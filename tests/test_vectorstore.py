"""Tests for infrastructure/rag/vectorstore.py."""

from infrastructure.rag.vectorstore import (
    _build_vectorstore,
    _chroma_dir_for_provider,
    _build_chroma_filter,
    _doc_matches_filters,
    _extract_doc_metadata,
    _infer_query_metadata,
    _preferred_source_types,
    _rank_scored_docs,
    _score_doc,
    retrieve,
)


class TestChromaDirForProvider:
    def test_provider_gets_own_directory(self):
        assert str(_chroma_dir_for_provider("openai")).endswith("chroma_db/openai")
        assert str(_chroma_dir_for_provider("google")).endswith("chroma_db/google")


class TestBuildVectorstore:
    def test_uses_provider_specific_embeddings_and_directory(self, monkeypatch):
        captured = {}

        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.create_embeddings",
            lambda provider: f"embeddings:{provider}",
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._load_and_split_docs",
            lambda: ["doc1"],
        )

        class FakeChroma:
            def __init__(self, persist_directory, embedding_function):
                captured["embedding"] = embedding_function
                captured["persist_directory"] = persist_directory

            def add_documents(self, documents):
                captured["documents"] = documents

        monkeypatch.setattr("infrastructure.rag.vectorstore.Chroma", FakeChroma)

        result = _build_vectorstore(provider="google", force_rebuild=True)

        assert isinstance(result, FakeChroma)
        assert captured["documents"] == ["doc1"]
        assert captured["embedding"] == "embeddings:google"
        assert captured["persist_directory"].endswith("chroma_db/google")


class TestRetrieve:
    def test_passes_provider_through_to_vectorstore(self, monkeypatch):
        calls = {}

        class FakeVectorStore:
            def similarity_search(self, query, k, filter=None):
                calls.setdefault("similarity_search", []).append(
                    {"query": query, "k": k, "filter": filter}
                )
                return [
                    FakeDoc(
                        "chunk 2",
                        "knowledge_base/visa_requirements.md",
                        source_type="visa_requirements",
                        country="France",
                    ),
                ]

        class FakeDoc:
            def __init__(self, page_content, source, **metadata):
                self.page_content = page_content
                self.metadata = {"source": source, **metadata}

        class FakeBM25:
            def __init__(self, documents, k):
                calls.setdefault("bm25_inputs", []).append(
                    {"documents": documents, "k": k}
                )
                self.k = k

            def invoke(self, query):
                calls["query"] = query
                return [FakeDoc("chunk 3", "knowledge_base/visa_requirements.md", source_type="visa_requirements", country="France")]

        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._build_vectorstore",
            lambda provider=None, force_rebuild=False: (
                calls.__setitem__("provider", provider) or FakeVectorStore()
            ),
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._load_and_split_docs",
            lambda: [
                FakeDoc(
                    "bm25 visa chunk",
                    "knowledge_base/visa_requirements.md",
                    source_type="visa_requirements",
                    country="France",
                ),
            ],
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.BM25Retriever.from_documents",
            lambda chunks, k: FakeBM25(chunks, k),
        )

        result = retrieve(
            "What are the entry requirements for a US passport holder visiting Paris?",
            provider="google",
            k=2,
        )

        assert calls["provider"] == "google"
        assert calls["similarity_search"][0]["k"] == 8
        assert calls["similarity_search"][0]["filter"] == {
            "$and": [
                {"source_type": "visa_requirements"},
                {"$or": [{"city": "Paris"}, {"country": "France"}]},
            ]
        }
        assert all(
            doc.metadata.get("source_type") == "visa_requirements"
            for doc in calls["bm25_inputs"][0]["documents"]
        )
        assert calls["query"] == "What are the entry requirements for a US passport holder visiting Paris?"
        assert result == [
            {"content": "chunk 2", "source": "Visa Requirements"},
            {"content": "chunk 3", "source": "Visa Requirements"},
        ]


class TestMetadataExtraction:
    def test_extracts_visa_metadata_and_topics(self):
        metadata = _extract_doc_metadata(
            "knowledge_base/visa_requirements.md",
            "## France (Schengen Area)\n- **US citizens:** Visa-free for up to 90 days.\n- **Documents needed:** Passport valid 3+ months beyond stay.",
        )

        assert metadata["source_type"] == "visa_requirements"
        assert metadata["city"] == ""
        assert metadata["country"] == "France"
        assert "entry_requirements" in metadata["topics"]


class TestMetadataAwareRetrieval:
    def test_infers_country_from_manual_city_alias_for_visa_queries(self):
        result = _infer_query_metadata("Do Indian citizens need a visa for Dublin?")

        assert result["city"] == "Dublin"
        assert result["country"] == "Ireland"
        assert result["intents"] == ["entry_requirements"]

    def test_detects_document_questions_as_entry_requirements(self):
        result = _infer_query_metadata("What documents are needed to enter Japan for tourism?")

        assert "entry_requirements" in result["intents"]

    def test_entry_requirements_prefer_visa_sources(self):
        result = _preferred_source_types(
            {"intents": ["entry_requirements"], "city": "Paris", "country": "France"}
        )

        assert result == ["visa_requirements"]

    def test_builds_chroma_filter_with_source_and_place(self):
        result = _build_chroma_filter(
            query_meta={"city": "Paris", "country": "France", "intents": ["entry_requirements"]},
            allowed_source_types=["visa_requirements"],
            require_place_match=True,
        )

        assert result == {
            "$and": [
                {"source_type": "visa_requirements"},
                {"$or": [{"city": "Paris"}, {"country": "France"}]},
            ]
        }

    def test_country_level_match_keeps_visa_doc_without_city(self):
        assert _doc_matches_filters(
            {"source_type": "visa_requirements", "country": "France"},
            query_meta={"city": "Paris", "country": "France", "intents": ["entry_requirements"]},
            allowed_source_types=["visa_requirements"],
            require_place_match=True,
        ) is True

    def test_ranking_boosts_exact_destination_and_passport_matches(self):
        class FakeDoc:
            def __init__(self, page_content, source, **metadata):
                self.page_content = page_content
                self.metadata = {"source": source, **metadata}

        query_meta = _infer_query_metadata(
            "What are the entry requirements for a US passport holder visiting Paris?"
        )
        exact_doc = FakeDoc(
            "## France (Schengen Area)\n- **US citizens:** Visa-free for up to 90 days.\n- **Documents needed:** Passport valid 3+ months beyond stay.",
            "knowledge_base/visa_requirements.md",
            source_type="visa_requirements",
            country="France",
            heading="France (Schengen Area)",
        )
        noisy_doc = FakeDoc(
            "## Vietnam\n- **US citizens:** Visa required.\n- **Documents needed:** Passport valid 6+ months.",
            "knowledge_base/visa_requirements.md",
            source_type="visa_requirements",
            country="Vietnam",
            heading="Vietnam",
        )

        ranked = _rank_scored_docs(
            [
                (
                    _score_doc(
                        noisy_doc,
                        query_meta=query_meta,
                        allowed_source_types=["visa_requirements"],
                        retrieval_mode="vector",
                    ),
                    0,
                    noisy_doc,
                ),
                (
                    _score_doc(
                        exact_doc,
                        query_meta=query_meta,
                        allowed_source_types=["visa_requirements"],
                        retrieval_mode="bm25",
                    ),
                    1,
                    exact_doc,
                ),
            ],
            k=2,
        )

        assert ranked[0] is exact_doc
