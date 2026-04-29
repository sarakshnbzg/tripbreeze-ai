"""Tests for application/graph.py — HITL review, routing, and graph structure."""

from langgraph.checkpoint.memory import MemorySaver

from application.graph import (
    _route_after_intake,
    _route_after_review_router,
    build_graph,
    compile_graph,
)
from domain.nodes.hitl_review import (
    _markdown_table_value,
    _format_trip_summary,
    hitl_review,
)
from domain.nodes.review_router import _build_revision_baseline, build_revision_query, review_router
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
    def test_compiled_graph_does_not_use_interrupt_before(self, monkeypatch):
        """Review routing now pauses via a dynamic interrupt inside feedback_router."""
        monkeypatch.setattr("application.graph.get_checkpointer", lambda: MemorySaver())
        compiled = compile_graph()
        assert not compiled.interrupt_before_nodes


class TestBuildRevisionQuery:
    def test_includes_current_trip_and_feedback(self):
        query = build_revision_query(
            {
                "trip_request": {
                    "origin": "Berlin",
                    "destination": "Paris",
                    "departure_date": "2026-07-01",
                    "return_date": "2026-07-08",
                    "budget_limit": 1200,
                    "currency": "EUR",
                    "preferences": "direct flights",
                },
                "user_feedback": "Show cheaper hotel options and avoid layovers.",
            }
        )

        assert "Current origin: Berlin" in query
        assert "Current destination: Paris" in query
        assert "Budget limit: 1200 EUR" in query
        assert "Show cheaper hotel options and avoid layovers." in query


class TestRevisionBaseline:
    def test_updates_return_date_when_feedback_changes_nights(self):
        baseline = _build_revision_baseline(
            {
                "trip_request": {
                    "origin": "Berlin",
                    "destination": "London",
                    "departure_date": "2026-05-21",
                    "return_date": "2026-05-23",
                },
                "user_feedback": "Make the trip 5 nights",
            }
        )

        assert baseline["return_date"] == "2026-05-26"

    def test_review_router_uses_resumed_feedback_for_revision_baseline(self, monkeypatch):
        monkeypatch.setattr(
            "domain.nodes.review_router.interrupt",
            lambda payload: {
                "feedback_type": "revise_plan",
                "user_feedback": "Make it 5 nights",
            },
        )

        result = review_router(
            {
                "trip_request": {
                    "origin": "Berlin",
                    "destination": "London",
                    "departure_date": "2026-05-21",
                    "return_date": "2026-05-23",
                }
            }
        )

        assert result["free_text_query"] == "Make it 5 nights"
        assert result["revision_baseline"]["return_date"] == "2026-05-26"

    def test_review_router_clears_partial_results_state_when_revising(self, monkeypatch):
        monkeypatch.setattr(
            "domain.nodes.review_router.interrupt",
            lambda payload: {
                "feedback_type": "revise_plan",
                "user_feedback": "Try different dates with better flight availability",
            },
        )

        result = review_router(
            {
                "trip_request": {
                    "origin": "Berlin",
                    "destination": "Porto",
                    "departure_date": "2026-05-21",
                    "return_date": "2026-05-24",
                },
                "flight_options": [],
                "hotel_options": [{"name": "Harbor Hotel"}],
                "budget": {
                    "partial_results_note": "Hotel options are ready, but flight options are unavailable right now.",
                },
                "destination_info": "### Porto\nPartial briefing",
                "selected_hotel": {"name": "Harbor Hotel"},
                "final_itinerary": "Recovered trip",
                "itinerary_data": {"trip_overview": "Berlin to Porto"},
                "itinerary_cover": {"image_url": "/api/generated-images/cover.png"},
                "rag_sources": ["Visa Requirements"],
                "rag_trace": [{"node": "research"}],
            }
        )

        assert result["current_step"] == "revising_plan"
        assert result["free_text_query"] == "Try different dates with better flight availability"
        assert result["flight_options"] == []
        assert result["hotel_options"] == []
        assert result["budget"] == {}
        assert result["destination_info"] == ""
        assert result["selected_hotel"] == {}
        assert result["final_itinerary"] == ""
        assert result["itinerary_data"] == {}
        assert result["itinerary_cover"] == {}
        assert result["rag_sources"] == []
        assert result["rag_trace"] == []
        assert result["revision_baseline"]["destination"] == "Porto"


class TestRouteAfterIntake:
    def test_successful_intake_continues(self):
        assert _route_after_intake({"current_step": "intake_complete"}) == "continue"

    def test_out_of_domain_intake_stops(self):
        assert _route_after_intake({"current_step": "out_of_domain"}) == "stop"

    def test_validation_error_stops(self):
        assert _route_after_intake({"current_step": "intake_error"}) == "stop"


class TestRouteAfterReviewRouter:
    def test_revision_routes_back_to_intake(self):
        assert _route_after_review_router({"feedback_type": "revise_plan"}) == "revise"

    def test_cancel_routes_to_end(self):
        assert _route_after_review_router({"feedback_type": "cancel"}) == "stop"

    def test_approval_routes_to_finalisation_path(self):
        assert _route_after_review_router({"feedback_type": "rewrite_itinerary"}) == "approve"


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
            "destination_info": "A quick travel snapshot to help you compare options and plan the stay:\n\n#### 🛂 Entry Requirements\nCheck passport validity before travel.",
            "rag_used": True,
            "rag_sources": ["Visa Requirements"],
        }
        result = hitl_review(state)
        content = result["messages"][0]["content"]
        assert "### Destination Briefing" in content
        assert "#### 🛂 Entry Requirements" in content
        assert "Check passport validity before travel" in content
        assert "_Source: Visa Requirements_" in content

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
        """Only entry requirements are shown in the initial grounded result."""
        result = _format_destination_info(
            {
                "entry_requirements": "Check passport validity before travel. (Source: Visa Requirements)",
            }
        )

        assert "A quick travel snapshot" in result
        assert "#### 🛂 Entry Requirements" in result
        assert "Check passport validity" in result

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
            "feedback_router",
            "attractions",
            "finalise",
            "update_memory",
        }
        assert expected.issubset(node_names)

    def test_compile_graph_returns_runnable(self, monkeypatch):
        monkeypatch.setattr("application.graph.get_checkpointer", lambda: MemorySaver())
        compiled = compile_graph()
        assert hasattr(compiled, "stream")
        assert hasattr(compiled, "invoke")
