"""Tests for domain/nodes/trip_finaliser.py."""

from domain.nodes.trip_finaliser import (
    render_itinerary_markdown,
    Itinerary,
    Source,
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
        assert "Sources" in md
        assert "destinations.md" in md
        assert "visa_requirements.md" in md
        assert "Paris is a top destination" in md

    def test_no_sources_section_when_empty(self):
        md = render_itinerary_markdown(self._sample_itinerary(sources=[]))
        assert "Sources" not in md

    def test_sections_separated_by_blank_lines(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "\n\n" in md


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
