"""Tests for application/graph.py — HITL review, routing, and graph structure."""

from application.graph import (
    _route_after_intake,
    build_graph,
    compile_graph,
    run_finalisation_streaming,
)
from domain.nodes.hitl_review import (
    _markdown_table_value,
    _format_trip_summary,
    hitl_review,
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


# ── _route_after_review / interrupt behavior ──


class TestGraphInterrupt:
    def test_compiled_graph_has_interrupt_before_finalise(self):
        """The compiled graph must pause before 'finalise' so HITL review can happen."""
        compiled = compile_graph()
        assert "finalise" in compiled.interrupt_before_nodes


class TestRouteAfterIntake:
    def test_successful_intake_continues(self):
        assert _route_after_intake({"current_step": "intake_complete"}) == "continue"

    def test_out_of_domain_intake_stops(self):
        assert _route_after_intake({"current_step": "out_of_domain"}) == "stop"

    def test_validation_error_stops(self):
        assert _route_after_intake({"current_step": "intake_error"}) == "stop"


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

    def test_does_not_duplicate_next_step_in_review_message(self):
        state = {"trip_request": {}, "flight_options": [], "hotel_options": []}
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "### Next Step" not in content
        assert "approve to generate the final itinerary" not in content


# ── destination info formatting ──


class TestDestinationInfoFormatting:
    def test_formats_structured_destination_sections(self):
        """Only overview and entry requirements are shown in initial result.

        Transport tips, safety notes, and budget tips are deferred to the final itinerary.
        """
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
        # transport_tips is now deferred to final itinerary
        assert "#### 🚇 Getting Around" not in result
        assert "Tokyo is strong" in result
        assert "Check passport validity" in result
        # transport content should not appear in initial result
        assert "Use trains" not in result

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
            "research",
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


# ── run_finalisation_streaming ──


class TestRunFinalisationStreaming:
    def test_callable_with_correct_signature(self):
        """run_finalisation_streaming must accept (graph, thread_id, state_updates)."""
        import inspect
        sig = inspect.signature(run_finalisation_streaming)
        params = list(sig.parameters)
        assert params == ["graph", "thread_id", "state_updates"]

    def test_streams_itinerary_chunks_before_final_state(self, monkeypatch):
        class DummyGraph:
            def __init__(self):
                self.state = {"trip_request": {"destination": "Paris"}}

            def update_state(self, config, updates, as_node=None):
                self.state.update(updates)

            def get_state(self, config):
                from types import SimpleNamespace
                return SimpleNamespace(values=self.state)

            def stream(self, initial_state, config):
                yield {}

        monkeypatch.setattr(
            "domain.nodes.attractions_research.attractions_research",
            lambda state: {"attraction_candidates": []},
        )
        monkeypatch.setattr(
            "application.graph.trip_finaliser",
            lambda state: {"final_itinerary": "Hello Paris", "current_step": "finalised"},
        )

        items = list(run_finalisation_streaming(DummyGraph(), "thread-123", {"user_approved": True}))

        assert items[:-1] == ["Hello", " ", "Paris"]
        assert items[-1]["final_itinerary"] == "Hello Paris"
