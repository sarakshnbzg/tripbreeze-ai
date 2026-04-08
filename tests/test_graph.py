"""Tests for application/graph.py — HITL review, routing, and graph structure."""

from application.graph import (
    _markdown_table_value,
    _format_trip_summary,
    _route_after_review,
    hitl_review,
    build_graph,
    compile_graph,
    run_finalisation,
)
from domain.nodes.research_orchestrator import _format_destination_info


# ── _format_trip_summary ──


class TestFormatTripSummary:
    def test_round_trip(self):
        trip = {
            "origin": "London",
            "destination": "Paris",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-08",
            "num_travelers": 2,
            "travel_class": "BUSINESS",
        }
        result = _format_trip_summary(trip, [], [])
        assert "### Trip Summary" in result
        assert "| Detail | Selection |" in result
        assert "London -> Paris" in result
        assert "| Trip type | Round trip |" in result
        assert "2026-07-01 to 2026-07-08" in result
        assert "| Nights | 7 |" in result
        assert "2" in result
        assert "Business" in result

    def test_one_way(self):
        trip = {
            "origin": "NYC",
            "destination": "LAX",
            "departure_date": "2026-08-01",
            "check_out_date": "2026-08-05",
            "num_travelers": 1,
        }
        result = _format_trip_summary(trip, [], [])
        assert "| Trip type | One-way |" in result
        assert "one-way" in result
        assert "NYC -> LAX" in result
        assert "| Nights | 4 |" in result

    def test_missing_fields_show_question_marks(self):
        result = _format_trip_summary({}, [], [])
        assert "? -> ?" in result

    def test_premium_economy_formatted(self):
        trip = {"travel_class": "PREMIUM_ECONOMY"}
        result = _format_trip_summary(trip, [], [])
        assert "Premium Economy" in result

    def test_markdown_table_values_escape_pipes(self):
        assert _markdown_table_value("Paris | Tokyo") == "Paris \\| Tokyo"


# ── _route_after_review ──


class TestRouteAfterReview:
    def test_approved_routes_to_finalise(self):
        assert _route_after_review({"user_approved": True}) == "finalise"

    def test_not_approved_routes_to_awaiting(self):
        assert _route_after_review({"user_approved": False}) == "awaiting_input"

    def test_missing_approval_routes_to_awaiting(self):
        assert _route_after_review({}) == "awaiting_input"


# ── hitl_review ──


class TestHitlReview:
    def test_includes_trip_summary(self):
        state = {
            "trip_request": {"origin": "London", "destination": "Tokyo"},
            "flight_options": [],
            "hotel_options": [],
        }
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "London -> Tokyo" in content
        assert result["current_step"] == "awaiting_review"

    def test_includes_destination_info_with_sources(self):
        state = {
            "trip_request": {},
            "flight_options": [],
            "hotel_options": [],
            "destination_info": "A quick travel snapshot to help you compare options and plan the stay:\n\n#### 🌍 Overview\nGreat city to visit.",
            "rag_used": True,
            "rag_sources": ["Destinations", "Travel Tips"],
        }
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "### Destination Briefing" in content
        assert "#### 🌍 Overview" in content
        assert "Great city to visit" in content
        assert "_Source: Destinations, Travel Tips_" in content

    def test_rag_used_without_dest_info(self):
        state = {
            "trip_request": {},
            "flight_options": [],
            "hotel_options": [],
            "destination_info": "",
            "rag_used": True,
        }
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "### Destination Briefing" in content
        assert "no destination briefing text was produced" in content

    def test_budget_notes_included(self):
        state = {
            "trip_request": {},
            "flight_options": [],
            "hotel_options": [],
            "budget": {"budget_notes": "You're within budget."},
        }
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "### Budget Note" in content
        assert "You're within budget" in content

    def test_next_step_always_present(self):
        state = {"trip_request": {}, "flight_options": [], "hotel_options": []}
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "### Next Step" in content
        assert "approve to generate the final itinerary" in content


# ── destination info formatting ──


class TestDestinationInfoFormatting:
    def test_formats_structured_destination_sections(self):
        result = _format_destination_info(
            {
                "destination_overview": "Tokyo is strong for food and transit. (Source: Destinations)",
                "entry_requirements": "Check passport validity before travel. (Source: Visa Requirements)",
                "transport_tips": "Use trains for most city travel. (Source: Travel Tips)",
            }
        )

        assert "A quick travel snapshot" in result
        assert "#### 🌍 Overview" in result
        assert "#### 🛂 Entry Requirements" in result
        assert "#### 🚇 Getting Around" in result
        assert "Tokyo is strong" in result
        assert "Check passport validity" in result
        assert "Use trains" in result

    def test_falls_back_to_legacy_destination_briefing(self):
        result = _format_destination_info(
            {"destination_briefing": "Great city to visit. (Source: Destinations)"}
        )

        assert result == "Great city to visit. (Source: Destinations)"


# ── build_graph / compile_graph ──


class TestGraphConstruction:
    def test_build_graph_has_expected_nodes(self):
        graph = build_graph()
        node_names = set(graph.nodes.keys())
        expected = {
            "load_profile",
            "trip_intake",
            "flight_search",
            "hotel_search",
            "destination_research",
            "aggregate_budget",
            "review",
            "finalise",
            "update_memory",
        }
        assert expected.issubset(node_names)

    def test_compile_graph_returns_runnable(self):
        compiled = compile_graph()
        assert hasattr(compiled, "stream")
        assert hasattr(compiled, "invoke")


# ── run_finalisation ──


class TestRunFinalisation:
    def test_calls_finaliser_and_memory_updater(self, monkeypatch):
        calls = []

        def fake_finaliser(state):
            calls.append("finaliser")
            return {"final_itinerary": "Your trip is ready."}

        def fake_updater(state):
            calls.append("updater")
            return {"current_step": "done"}

        monkeypatch.setattr("application.graph.trip_finaliser", fake_finaliser)
        monkeypatch.setattr("application.graph.memory_updater", fake_updater)

        state = {"user_id": "test", "trip_request": {}}
        result = run_finalisation(state)

        assert calls == ["finaliser", "updater"]
        assert result["final_itinerary"] == "Your trip is ready."
        assert result["current_step"] == "done"
