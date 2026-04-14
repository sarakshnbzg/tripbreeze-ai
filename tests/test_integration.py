"""Integration tests — run the full or partial LangGraph pipeline with mocked external services.

These tests verify that nodes are wired correctly, state flows between them,
routing logic works, and errors propagate without crashing the pipeline.
All external I/O (LLM, SerpAPI, Postgres, RAG) is mocked at the infrastructure boundary.
"""

from __future__ import annotations

import contextlib
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import uuid

import pytest

from application.graph import compile_graph, run_finalisation_streaming
from domain.nodes.trip_finaliser import Itinerary


# ── Future dates (always valid) ──────────────────────────────────────

_TODAY = date.today()
FUTURE_DEPARTURE = (_TODAY + timedelta(days=30)).isoformat()
FUTURE_RETURN = (_TODAY + timedelta(days=37)).isoformat()


# ── Fake data factories ──────────────────────────────────────────────


def _fake_profile(**overrides: Any) -> dict[str, Any]:
    base = {
        "home_city": "Berlin",
        "travel_class": "ECONOMY",
        "preferred_hotel_stars": [3, 4],
        "passport_country": "Germany",
        "preferred_airlines": [],
        "past_trips": [
            {"destination": "Rome", "departure_date": "2024-09-10"},
        ],
    }
    base.update(overrides)
    return base


def _fake_flights() -> list[dict]:
    return [
        {
            "airline": "Air France",
            "departure_time": "08:00",
            "arrival_time": "10:30",
            "duration": "2h 30m",
            "stops": 0,
            "price": 180.0,
            "total_price": 360.0,
            "currency": "EUR",
            "outbound_summary": "CDG 08:00 → LHR 10:30",
            "return_summary": "LHR 18:00 → CDG 20:30",
            "adults": 2,
        },
        {
            "airline": "Lufthansa",
            "departure_time": "14:00",
            "arrival_time": "16:45",
            "duration": "2h 45m",
            "stops": 1,
            "price": 150.0,
            "total_price": 300.0,
            "currency": "EUR",
            "outbound_summary": "FRA 14:00 → CDG 16:45",
            "return_summary": "CDG 19:00 → FRA 21:30",
            "adults": 2,
        },
    ]


def _fake_hotels() -> list[dict]:
    return [
        {
            "name": "Hotel Le Marais",
            "description": "12 Rue de Rivoli, Paris",
            "hotel_class": 4,
            "rating": 8.5,
            "price_per_night": 120.0,
            "total_price": 840.0,
            "currency": "EUR",
            "check_in": FUTURE_DEPARTURE,
            "check_out": FUTURE_RETURN,
        },
        {
            "name": "Ibis Budget Paris",
            "description": "5 Rue Voltaire, Paris",
            "hotel_class": 2,
            "rating": 7.0,
            "price_per_night": 65.0,
            "total_price": 455.0,
            "currency": "EUR",
            "check_in": FUTURE_DEPARTURE,
            "check_out": FUTURE_RETURN,
        },
    ]


def _make_ai_message(tool_calls: list[dict] | None = None, content: str = "") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    return msg


def _base_structured_fields(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "origin": "London",
        "destination": "Paris",
        "departure_date": FUTURE_DEPARTURE,
        "return_date": FUTURE_RETURN,
        "num_travelers": 2,
        "budget_limit": 3000,
        "currency": "EUR",
        "travel_class": "ECONOMY",
        "preferences": "",
        "hotel_stars": [],
    }
    fields.update(overrides)
    return fields


def _base_initial_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "user_id": "test_user",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "structured_fields": _base_structured_fields(),
        "free_text_query": "",
        "messages": [],
        "token_usage": [],
    }
    state.update(overrides)
    return state



def _make_config() -> dict:
    """Return a LangGraph config with a unique thread_id (required by MemorySaver)."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}

# ── Mock builders ────────────────────────────────────────────────────


def _research_llm_mock(flights: list[dict], hotels: list[dict]) -> MagicMock:
    """Build a mock LLM that simulates the ReAct loop:
    1st call → search_flights + search_hotels
    2nd call → SubmitResearchResult
    """
    call_tools = _make_ai_message(tool_calls=[
        {"name": "search_flights", "args": {}, "id": "c1"},
        {"name": "search_hotels", "args": {}, "id": "c2"},
    ])
    submit = _make_ai_message(tool_calls=[{
        "name": "SubmitResearchResult",
        "args": {
            "summary": f"Found {len(flights)} flights and {len(hotels)} hotels.",
            "destination_overview": "Paris is the capital of France.",
        },
        "id": "c3",
    }])

    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.side_effect = [call_tools, submit]
    return mock_llm


def _finaliser_llm_mock() -> MagicMock:
    """Mock for ReAct-style finaliser that calls Itinerary tool directly."""
    mock_llm = MagicMock()

    # First call: LLM decides to submit the Itinerary directly (no RAG needed)
    submit_response = MagicMock()
    submit_response.tool_calls = [
        {
            "id": "call_final",
            "name": "Itinerary",
            "args": {
                "trip_overview": "London to Paris, 7 nights",
                "flight_details": "- Air France direct\n- 2h 30m",
                "hotel_details": "- Hotel Le Marais\n- 4-star",
                "destination_highlights": "Eiffel Tower, Louvre Museum",
                "daily_plans": [],
                "budget_breakdown": "Total: 1500 EUR",
                "visa_entry_info": "No visa needed for EU/UK passport holders",
                "packing_tips": "Pack layers for spring weather",
                "sources": [],
            },
        }
    ]
    submit_response.usage_metadata = {"input_tokens": 100, "output_tokens": 200}

    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = submit_response

    return mock_llm


# ── Patch context manager ────────────────────────────────────────────


@contextlib.contextmanager
def _patch_all(
    profile: dict | None = None,
    flights: list[dict] | None = None,
    hotels: list[dict] | None = None,
    intake_llm: MagicMock | None = None,
    research_llm: MagicMock | None = None,
    finaliser_llm: MagicMock | None = None,
):
    """Patch all external services at the module-import boundary."""
    _profile = profile if profile is not None else _fake_profile()
    _flights = flights if flights is not None else _fake_flights()
    _hotels = hotels if hotels is not None else _fake_hotels()
    _research = research_llm or _research_llm_mock(_flights, _hotels)
    _finaliser = finaliser_llm or _finaliser_llm_mock()

    with (
        patch("domain.nodes.profile_loader.load_profile", return_value=_profile) as mock_profile,
        patch("domain.agents.flight_agent.api_search_flights", return_value=_flights) as mock_api_flights,
        patch("domain.agents.hotel_agent.api_search_hotels", return_value=_hotels) as mock_api_hotels,
        patch("domain.nodes.research_orchestrator.retrieve", return_value=[]) as mock_rag,
        patch("domain.nodes.trip_finaliser.retrieve", return_value=[]) as mock_finaliser_rag,
        patch("domain.nodes.research_orchestrator.create_chat_model", return_value=_research) as mock_research_llm,
        patch("domain.nodes.trip_finaliser.create_chat_model", return_value=_finaliser) as mock_final_llm,
        patch("domain.nodes.trip_intake.create_chat_model") as mock_intake_llm,
        patch("domain.nodes.memory_updater.update_profile_from_trip", return_value=_profile) as mock_memory,
    ):
        if intake_llm is not None:
            mock_intake_llm.return_value = intake_llm

        yield {
            "load_profile": mock_profile,
            "api_flights": mock_api_flights,
            "api_hotels": mock_api_hotels,
            "rag": mock_rag,
            "research_llm": mock_research_llm,
            "finaliser_llm": mock_final_llm,
            "intake_llm": mock_intake_llm,
            "memory": mock_memory,
        }


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestFullPipelineToReview:
    """Structured fields → profile_loader → trip_intake → research → budget → review (HITL stop)."""

    def test_reaches_awaiting_review(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        assert result["current_step"] == "awaiting_review"

    def test_trip_request_populated(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        trip = result["trip_request"]
        assert trip["origin"] == "London"
        assert trip["destination"] == "Paris"
        assert trip["departure_date"] == FUTURE_DEPARTURE
        assert trip["return_date"] == FUTURE_RETURN
        assert trip["num_travelers"] == 2
        assert trip["currency"] == "EUR"

    def test_flight_and_hotel_options_present(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        assert len(result["flight_options"]) > 0
        assert len(result["hotel_options"]) > 0

    def test_budget_computed(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        budget = result["budget"]
        assert "within_budget" in budget
        assert "flight_cost" in budget
        assert "hotel_cost" in budget
        assert budget["currency"] == "EUR"

    def test_user_profile_loaded(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        assert result["user_profile"]["home_city"] == "Berlin"
        mocks["load_profile"].assert_called_once_with("test_user")

    def test_messages_accumulated(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        assert len(result["messages"]) >= 3  # profile + intake + research + budget + review

    def test_finaliser_not_called(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        mocks["finaliser_llm"].assert_not_called()
        mocks["memory"].assert_not_called()


class TestRunFinalisation:
    """After user approves, run_finalisation_streaming resumes the graph through finalise + memory."""

    def test_produces_final_itinerary(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            thread_id = "test-finalisation-itinerary"
            config = {"configurable": {"thread_id": thread_id}}
            graph.invoke(_base_initial_state(), config)

            state_updates = {
                "user_approved": True,
                "selected_flight": _fake_flights()[0],
                "selected_hotel": _fake_hotels()[0],
            }
            items = list(run_finalisation_streaming(graph, thread_id, state_updates))

        final_state = next((i for i in items if isinstance(i, dict)), None)
        assert final_state is not None
        assert final_state.get("final_itinerary")

    def test_memory_updater_called(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            thread_id = "test-finalisation-memory"
            config = {"configurable": {"thread_id": thread_id}}
            graph.invoke(_base_initial_state(), config)

            state_updates = {
                "user_approved": True,
                "selected_flight": _fake_flights()[0],
                "selected_hotel": _fake_hotels()[0],
            }
            list(run_finalisation_streaming(graph, thread_id, state_updates))

        mocks["memory"].assert_called_once()
        call_args = mocks["memory"].call_args
        assert call_args[0][0] == "test_user"


class TestFullPipelineWithApproval:
    """Full pipeline: initial planning pauses at interrupt, then resumes via run_finalisation_streaming."""

    def test_reaches_finalised(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            thread_id = "test-full-approval"
            config = {"configurable": {"thread_id": thread_id}}

            # Phase 1: planning runs to HITL interrupt
            result = graph.invoke(_base_initial_state(), config)
            assert result["current_step"] == "awaiting_review"

            # Phase 2: user approves; graph resumes through finalise + memory_updater
            state_updates = {
                "user_approved": True,
                "selected_flight": _fake_flights()[0],
                "selected_hotel": _fake_hotels()[0],
            }
            items = list(run_finalisation_streaming(graph, thread_id, state_updates))

        final_state = next((i for i in items if isinstance(i, dict)), None)
        assert final_state is not None
        assert final_state.get("final_itinerary")
        mocks["memory"].assert_called_once()


class TestIntakeValidationStopsGraph:
    """Validation errors in trip_intake should route to END without running research."""

    def test_return_before_departure(self):
        fields = _base_structured_fields(
            departure_date=FUTURE_RETURN,
            return_date=FUTURE_DEPARTURE,
        )
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(structured_fields=fields), _make_config())

        assert result["current_step"] == "intake_error"
        assert "Return date" in result["error"] or "after departure" in result["error"]
        mocks["api_flights"].assert_not_called()
        mocks["api_hotels"].assert_not_called()

    def test_one_way_without_checkout_defaults_to_seven_nights(self):
        fields = _base_structured_fields(return_date="", check_out_date="")
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(structured_fields=fields), _make_config())

        # One-way trips without a check-out date now default to a 7-night stay
        assert result["current_step"] == "awaiting_review"
        assert result["trip_request"]["check_out_date"] != ""
        mocks["api_flights"].assert_called_once()

    def test_past_departure_date(self):
        yesterday = (_TODAY - timedelta(days=1)).isoformat()
        fields = _base_structured_fields(departure_date=yesterday)
        with _patch_all() as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(structured_fields=fields), _make_config())

        assert result["current_step"] == "intake_error"
        assert "past" in result["error"].lower()


class TestOutOfDomainGuardrail:
    """Free-text queries outside travel domain should be rejected early."""

    def test_non_travel_query_rejected(self):
        # Build a mock LLM for the intake node that classifies as out-of-domain
        domain_response = _make_ai_message(tool_calls=[{
            "name": "EvaluateDomain",
            "args": {"in_domain": False, "reason": "Not a travel request"},
            "id": "d1",
        }])
        intake_llm = MagicMock()
        intake_llm.bind_tools.return_value = intake_llm
        intake_llm.invoke.return_value = domain_response

        with _patch_all(intake_llm=intake_llm) as mocks:
            graph = compile_graph()
            state = _base_initial_state(
                structured_fields={},
                free_text_query="Explain quantum physics to me",
            )
            result = graph.invoke(state, _make_config())

        assert result["current_step"] == "out_of_domain"
        mocks["api_flights"].assert_not_called()
        mocks["api_hotels"].assert_not_called()


class TestSerpAPIFailure:
    """External API failures should not crash the pipeline."""

    def test_flight_search_failure_continues(self):
        with _patch_all() as mocks:
            mocks["api_flights"].side_effect = RuntimeError("SerpAPI unavailable")
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        # Pipeline should not crash — flight_agent catches the exception
        assert result["current_step"] == "awaiting_review"
        # Budget aggregator filters out all options when flights are empty
        # (no viable combination exists), so both lists end up empty
        assert result["budget"]["flights_before_budget_filter"] == 0
        assert "No flight and hotel combinations" in result["budget"]["budget_notes"]

    def test_hotel_search_failure_continues(self):
        with _patch_all() as mocks:
            mocks["api_hotels"].side_effect = RuntimeError("SerpAPI unavailable")
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        assert result["current_step"] == "awaiting_review"
        assert result["budget"]["hotels_before_budget_filter"] == 0
        assert "No flight and hotel combinations" in result["budget"]["budget_notes"]


class TestBudgetFiltering:
    """Budget aggregator filters options that exceed the budget."""

    def test_low_budget_filters_all_options(self):
        expensive_flights = [dict(f, price=5000.0, total_price=10000.0) for f in _fake_flights()]
        expensive_hotels = [dict(h, price_per_night=800.0, total_price=5600.0) for h in _fake_hotels()]

        with _patch_all(flights=expensive_flights, hotels=expensive_hotels) as mocks:
            graph = compile_graph()
            state = _base_initial_state(
                structured_fields=_base_structured_fields(budget_limit=100),
            )
            result = graph.invoke(state, _make_config())

        assert result["current_step"] == "awaiting_review"
        assert result["flight_options"] == []
        assert result["hotel_options"] == []
        assert "No flight and hotel combinations" in result["budget"]["budget_notes"]

    def test_generous_budget_keeps_options(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            state = _base_initial_state(
                structured_fields=_base_structured_fields(budget_limit=50000),
            )
            result = graph.invoke(state, _make_config())

        assert result["current_step"] == "awaiting_review"
        assert len(result["flight_options"]) > 0
        assert len(result["hotel_options"]) > 0
        assert result["budget"]["within_budget"] is True

    def test_no_budget_keeps_all_options(self):
        with _patch_all() as mocks:
            graph = compile_graph()
            state = _base_initial_state(
                structured_fields=_base_structured_fields(budget_limit=0),
            )
            result = graph.invoke(state, _make_config())

        assert result["current_step"] == "awaiting_review"
        assert len(result["flight_options"]) > 0
        assert len(result["hotel_options"]) > 0


class TestProfileDefaults:
    """Profile data should fill in missing fields."""

    def test_profile_home_city_used_as_origin(self):
        fields = _base_structured_fields(origin="")
        with _patch_all(profile=_fake_profile(home_city="Munich")) as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(structured_fields=fields), _make_config())

        assert result["trip_request"]["origin"] == "Munich"

    def test_profile_travel_class_used_as_default(self):
        fields = _base_structured_fields(travel_class="")
        with _patch_all(profile=_fake_profile(travel_class="BUSINESS")) as mocks:
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(structured_fields=fields), _make_config())

        assert result["trip_request"]["travel_class"] == "BUSINESS"


class TestRAGIntegration:
    """RAG retrieval results flow through to the review step."""

    def test_rag_sources_propagated(self):
        rag_results = [
            {"content": "Paris is lovely in spring.", "source": "destinations.md"},
            {"content": "No visa needed for EU citizens.", "source": "visa_requirements.md"},
        ]
        # Build research LLM that also calls retrieve_knowledge
        call_tools = _make_ai_message(tool_calls=[
            {"name": "search_flights", "args": {}, "id": "c1"},
            {"name": "search_hotels", "args": {}, "id": "c2"},
        ])
        call_rag = _make_ai_message(tool_calls=[
            {"name": "retrieve_knowledge", "args": {"query": "Paris travel info"}, "id": "c3"},
        ])
        submit = _make_ai_message(tool_calls=[{
            "name": "SubmitResearchResult",
            "args": {
                "summary": "Research complete with RAG.",
                "destination_overview": "Paris is lovely in spring.",
            },
            "id": "c4",
        }])

        research_llm = MagicMock()
        research_llm.bind_tools.return_value = research_llm
        research_llm.invoke.side_effect = [call_tools, call_rag, submit]

        with _patch_all(research_llm=research_llm) as mocks:
            mocks["rag"].return_value = rag_results
            graph = compile_graph()
            result = graph.invoke(_base_initial_state(), _make_config())

        assert result["rag_used"] is True
        assert "destinations.md" in result["rag_sources"]
        assert "visa_requirements.md" in result["rag_sources"]
        assert result["destination_info"]  # non-empty
