"""Tests for infrastructure/rag/vectorstore.py."""

from types import SimpleNamespace

from infrastructure.rag.vectorstore import (
    _build_vectorstore,
    _chroma_dir_for_provider,
    _extract_doc_metadata,
    _rerank_docs_for_query,
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
        import infrastructure.rag.vectorstore as vs_module

        # Clear cached BM25 so from_documents is called
        monkeypatch.setattr(vs_module, "_cached_bm25", None)

        calls = {}

        class FakeVectorStore:
            def as_retriever(self, search_kwargs):
                calls["search_kwargs"] = search_kwargs
                return "vector_retriever"

        class FakeDoc:
            def __init__(self, page_content, source):
                self.page_content = page_content
                self.metadata = {"source": source}

        class FakeBM25:
            def __init__(self, k):
                self.k = k

        class FakeEnsembleRetriever:
            def __init__(self, retrievers, weights):
                calls["retrievers"] = retrievers
                calls["weights"] = weights

            def invoke(self, query):
                calls["query"] = query
                return [
                    FakeDoc("chunk 1", "knowledge_base/destinations.md"),
                    FakeDoc("chunk 2", "knowledge_base/visa_requirements.md"),
                ]

        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._build_vectorstore",
            lambda provider=None, force_rebuild=False: (
                calls.__setitem__("provider", provider) or FakeVectorStore()
            ),
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._load_and_split_docs",
            lambda: ["doc1", "doc2"],
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.BM25Retriever.from_documents",
            lambda chunks, k: FakeBM25(k),
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.EnsembleRetriever",
            FakeEnsembleRetriever,
        )

        result = retrieve("visa query", provider="google", k=2)

        assert calls["provider"] == "google"
        assert calls["search_kwargs"] == {"k": 8}
        assert calls["query"] == "visa query"
        assert result == [
            {"content": "chunk 1", "source": "Destinations"},
            {"content": "chunk 2", "source": "Visa Requirements"},
        ]


class TestMetadataExtraction:
    def test_extracts_destination_metadata_and_topics(self):
        metadata = _extract_doc_metadata(
            "knowledge_base/destinations.md",
            "## Amsterdam, Netherlands\n- **Local transport:** Cycling is king.\n- **Budget tip:** Walk the canals.",
        )

        assert metadata["source_type"] == "destinations"
        assert metadata["city"] == "Amsterdam"
        assert metadata["country"] == "Netherlands"
        assert "transport" in metadata["topics"]
        assert "budget" in metadata["topics"]


class TestReranking:
    def test_city_and_topic_match_beats_wrong_city_chunk(self):
        docs = [
            SimpleNamespace(
                page_content="- **Local transport:** RapidKL is cheap.",
                metadata={
                    "source": "knowledge_base/destinations.md",
                    "source_type": "destinations",
                    "city": "Kuala Lumpur",
                    "country": "Malaysia",
                    "topics": ["transport", "budget"],
                },
            ),
            SimpleNamespace(
                page_content="- **Local transport:** Cycling is king in Amsterdam.",
                metadata={
                    "source": "knowledge_base/destinations.md",
                    "source_type": "destinations",
                    "city": "Amsterdam",
                    "country": "Netherlands",
                    "topics": ["transport", "budget"],
                },
            ),
        ]

        result = _rerank_docs_for_query(docs, "Give me budget and transport tips for Amsterdam.", 2)

        assert result[0].metadata["city"] == "Amsterdam"

    def test_entry_requirements_prefers_visa_documents(self):
        docs = [
            SimpleNamespace(
                page_content="## Paris, France\n- **Best time to visit:** Spring.",
                metadata={
                    "source": "knowledge_base/destinations.md",
                    "source_type": "destinations",
                    "city": "Paris",
                    "country": "France",
                    "topics": ["destination_overview"],
                },
            ),
            SimpleNamespace(
                page_content="## France (Schengen Area)\n- **US citizens:** Visa-free for up to 90 days.",
                metadata={
                    "source": "knowledge_base/visa_requirements.md",
                    "source_type": "visa_requirements",
                    "city": "",
                    "country": "France",
                    "topics": ["entry_requirements"],
                },
            ),
        ]

        result = _rerank_docs_for_query(docs, "What are the entry requirements for a US passport holder visiting Paris?", 2)

        assert result[0].metadata["source_type"] == "visa_requirements"

    def test_diversifies_when_supporting_source_is_relevant(self):
        docs = [
            SimpleNamespace(
                page_content="## France (Schengen Area)\n- **US citizens:** Visa-free for up to 90 days.",
                metadata={
                    "source": "knowledge_base/visa_requirements.md",
                    "source_type": "visa_requirements",
                    "heading": "France (Schengen Area)",
                    "city": "",
                    "country": "France",
                    "topics": ["entry_requirements"],
                },
            ),
            SimpleNamespace(
                page_content="- **Documents needed:** Passport valid 3+ months beyond stay, return ticket.",
                metadata={
                    "source": "knowledge_base/visa_requirements.md",
                    "source_type": "visa_requirements",
                    "heading": "France (Schengen Area)",
                    "city": "",
                    "country": "France",
                    "topics": ["entry_requirements"],
                },
            ),
            SimpleNamespace(
                page_content="## General Travel Tips\n- Keep digital and physical copies of all travel documents.",
                metadata={
                    "source": "knowledge_base/travel_tips.md",
                    "source_type": "travel_tips",
                    "heading": "General Travel Tips",
                    "city": "",
                    "country": "",
                    "topics": ["entry_requirements", "packing"],
                },
            ),
        ]

        result = _rerank_docs_for_query(
            docs,
            "What are the entry requirements for a US passport holder visiting Paris?",
            3,
        )

        assert result[0].metadata["source_type"] == "visa_requirements"
        assert any(item.metadata["source_type"] == "travel_tips" for item in result[1:])
