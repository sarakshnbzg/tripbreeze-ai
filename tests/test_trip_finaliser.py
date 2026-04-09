"""Tests for domain/nodes/trip_finaliser.py."""

from unittest.mock import MagicMock, patch

from domain.nodes.trip_finaliser import (
    render_itinerary_markdown,
    Itinerary,
    Source,
    _selected_flight_context,
    trip_finaliser_stream,
)


class TestRenderItineraryMarkdown:
    def _sample_itinerary(self, **overrides):
        defaults = {
            "trip_overview": "London to Paris, July 1-8",
            "flight_details": "BA 123, direct",
            "hotel_details": "Hotel Le Marais, 4-star",
            "destination_highlights": "Eiffel Tower, Louvre",
            "budget_breakdown": "Flight: $500, Hotel: $800",
            "visa_entry_info": "No visa required for UK citizens",
            "packing_tips": "Bring an umbrella",
            "sources": [],
        }
        defaults.update(overrides)
        return Itinerary(**defaults)

    def test_all_sections_present(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "Trip Overview" in md
        assert "Flight Details" in md
        assert "Hotel Details" in md
        assert "Destination Highlights" in md
        assert "Budget Breakdown" in md
        assert "Visa & Entry Information" in md
        assert "Packing & Preparation Tips" in md

    def test_content_included(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "London to Paris" in md
        assert "BA 123" in md
        assert "Eiffel Tower" in md

    def test_sources_included_when_present(self):
        sources = [
            Source(document="destinations.md", snippet="Paris is a top destination"),
            Source(document="visa_requirements.md", snippet="No visa needed"),
        ]
        md = render_itinerary_markdown(self._sample_itinerary(sources=sources))
        assert "Sources (from Knowledge Base)" in md
        assert "destinations.md" in md
        assert "visa_requirements.md" in md
        assert "Paris is a top destination" in md

    def test_no_sources_section_when_empty(self):
        md = render_itinerary_markdown(self._sample_itinerary(sources=[]))
        assert "Sources" not in md

    def test_sections_separated_by_blank_lines(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "\n\n" in md

    def test_uses_smaller_section_headings(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert md.startswith("#### ✈️ Trip Overview\n")

    def test_flight_details_render_as_bullets_when_plain_text(self):
        md = render_itinerary_markdown(
            self._sample_itinerary(
                flight_details="BA 123 departs at 09:00. It is a direct flight. Baggage is included.",
            )
        )
        assert "#### 🛫 Flight Details" in md
        assert "- BA 123 departs at 09:00." in md
        assert "- It is a direct flight." in md
        assert "- Baggage is included." in md

    def test_hotel_details_preserve_existing_markdown_lists(self):
        md = render_itinerary_markdown(
            self._sample_itinerary(
                hotel_details="- Hotel Le Marais\n- 4-star stay\n- Breakfast included",
            )
        )
        assert "#### 🏨 Hotel Details" in md
        assert "- Hotel Le Marais" in md
        assert "- 4-star stay" in md
        assert "- Breakfast included" in md


class TestItineraryModel:
    def test_default_sources_empty(self):
        it = Itinerary(
            trip_overview="test",
            flight_details="test",
            hotel_details="test",
            destination_highlights="test",
            budget_breakdown="test",
            visa_entry_info="test",
            packing_tips="test",
        )
        assert it.sources == []

    def test_model_dump_roundtrip(self):
        it = Itinerary(
            trip_overview="overview",
            flight_details="flight",
            hotel_details="hotel",
            destination_highlights="highlights",
            budget_breakdown="budget",
            visa_entry_info="visa",
            packing_tips="packing",
            sources=[Source(document="doc.md", snippet="snippet")],
        )
        data = it.model_dump()
        restored = Itinerary(**data)
        assert restored.trip_overview == "overview"
        assert len(restored.sources) == 1
        assert restored.sources[0].document == "doc.md"


class TestSelectedFlightContext:
    def test_includes_outbound_and_return_summaries_for_round_trip(self):
        context = _selected_flight_context(
            {
                "airline": "Lufthansa",
                "outbound_summary": "BER 2026-04-09 08:00 -> LHR 2026-04-09 09:00",
                "return_summary": "LHR 2026-04-10 18:00 -> BER 2026-04-10 21:00",
                "selected_return": {"airline": "Lufthansa"},
            },
            {"return_date": "2026-04-10"},
        )
        assert "Outbound flight summary:" in context
        assert "Return flight summary:" in context
        assert "BER 2026-04-09 08:00" in context
        assert "LHR 2026-04-10 18:00" in context

    def test_omits_return_summary_for_one_way(self):
        context = _selected_flight_context(
            {"outbound_summary": "BER 2026-04-09 08:00 -> LHR 2026-04-09 09:00"},
            {},
        )
        assert "Outbound flight summary:" in context
        assert "Return flight summary:" not in context


class TestTripFinaliserStream:
    def _base_state(self):
        return {
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "trip_request": {
                "origin": "London",
                "destination": "Paris",
                "departure_date": "2026-07-01",
                "return_date": "2026-07-08",
                "currency": "EUR",
            },
            "selected_flight": {"airline": "Air France", "outbound_summary": "LHR -> CDG"},
            "selected_hotel": {"name": "Hotel Le Marais"},
            "destination_info": "Paris is lovely.",
            "rag_sources": [],
            "budget": {"total_estimated": 1500},
            "user_feedback": "",
        }

    @patch("domain.nodes.trip_finaliser.create_chat_model")
    def test_yields_string_chunks_then_final_dict(self, mock_create):
        chunk1 = MagicMock()
        chunk1.content = "#### ✈️ Trip Overview\n"
        chunk1.usage_metadata = {"input_tokens": 50, "output_tokens": 10}

        chunk2 = MagicMock()
        chunk2.content = "London to Paris, 7 nights"
        chunk2.usage_metadata = {"input_tokens": 0, "output_tokens": 8}

        mock_llm = MagicMock()
        mock_llm.stream.return_value = iter([chunk1, chunk2])
        mock_create.return_value = mock_llm

        items = list(trip_finaliser_stream(self._base_state()))

        # First items are string chunks
        string_chunks = [i for i in items if isinstance(i, str)]
        assert len(string_chunks) == 2
        assert "Trip Overview" in string_chunks[0]

        # Last item is the final state dict
        final = items[-1]
        assert isinstance(final, dict)
        assert "Trip Overview" in final["final_itinerary"]
        assert final["current_step"] == "finalised"
        assert final["token_usage"][0]["input_tokens"] == 50
        assert final["token_usage"][0]["output_tokens"] == 18

    @patch("domain.nodes.trip_finaliser.create_chat_model")
    def test_empty_content_chunks_are_skipped(self, mock_create):
        chunk_empty = MagicMock()
        chunk_empty.content = ""
        chunk_empty.usage_metadata = {}

        chunk_real = MagicMock()
        chunk_real.content = "Hello"
        chunk_real.usage_metadata = {"input_tokens": 10, "output_tokens": 5}

        mock_llm = MagicMock()
        mock_llm.stream.return_value = iter([chunk_empty, chunk_real])
        mock_create.return_value = mock_llm

        items = list(trip_finaliser_stream(self._base_state()))
        string_chunks = [i for i in items if isinstance(i, str)]
        assert string_chunks == ["Hello"]
