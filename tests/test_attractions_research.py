"""Tests for domain/nodes/attractions_research.py."""

from domain.nodes.attractions_research import attractions_research


class TestAttractionsResearch:
    def test_returns_empty_candidates_when_destination_missing(self):
        result = attractions_research({"trip_request": {}})

        assert result["attraction_candidates"] == []
        assert result["current_step"] == "attractions_complete"

    def test_populates_candidates_from_search(self, monkeypatch):
        def fake_search_attractions(destination, interests):
            assert destination == "Paris"
            assert interests == ["food", "art"]
            return [{"name": "Louvre"}, {"name": "Le Marais"}]

        monkeypatch.setattr(
            "domain.nodes.attractions_research.search_attractions",
            fake_search_attractions,
        )

        result = attractions_research(
            {"trip_request": {"destination": "Paris", "interests": ["food", "art"]}}
        )

        assert len(result["attraction_candidates"]) == 2
        assert result["attraction_candidates"][0]["name"] == "Louvre"

    def test_swallows_provider_exceptions(self, monkeypatch):
        def fake_search_attractions(*args, **kwargs):
            raise RuntimeError("provider down")

        monkeypatch.setattr(
            "domain.nodes.attractions_research.search_attractions",
            fake_search_attractions,
        )

        result = attractions_research({"trip_request": {"destination": "Paris"}})

        assert result["attraction_candidates"] == []
        assert result["current_step"] == "attractions_complete"
