"""Tests for infrastructure/rag/vectorstore.py."""

from infrastructure.rag.vectorstore import (
    _chroma_dir_for_provider,
    _build_chroma_filter,
    _doc_matches_filters,
    _extract_doc_metadata,
    _infer_query_metadata,
    _preferred_source_types,
    _rank_scored_docs,
    _score_doc,
)


class TestChromaDirForProvider:
    def test_provider_gets_own_directory(self):
        assert str(_chroma_dir_for_provider("openai")).endswith("chroma_db/openai")


class TestMetadataExtraction:
    def test_extracts_visa_metadata_and_topics(self):
        metadata = _extract_doc_metadata(
            "knowledge_base/visa_requirements/france.md",
            "---\ncountry: France\nsource_name: TripBreeze travel knowledge base\nsource_authority: manual_summary\nlast_verified: 2026-04-28\nreview_interval_days: 30\n---\n## France (Schengen Area)\n- **US citizens:** Visa-free for up to 90 days.\n- **Documents needed:** Passport valid 3+ months beyond stay.",
        )

        assert metadata["source_type"] == "visa_requirements"
        assert metadata["city"] == ""
        assert metadata["country"] == "France"
        assert metadata["source_name"] == "TripBreeze travel knowledge base"
        assert metadata["source_authority"] == "manual_summary"
        assert metadata["last_verified"] == "2026-04-28"
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
            "knowledge_base/visa_requirements/france.md",
            source_type="visa_requirements",
            country="France",
            heading="France (Schengen Area)",
        )
        noisy_doc = FakeDoc(
            "## Vietnam\n- **US citizens:** Visa required.\n- **Documents needed:** Passport valid 6+ months.",
            "knowledge_base/visa_requirements/vietnam.md",
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
