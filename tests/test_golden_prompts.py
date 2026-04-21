"""Golden-prompt replay tests for intake guardrails and itinerary quality."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from domain.nodes.trip_finaliser import trip_finaliser
from domain.nodes.trip_intake import trip_intake
from domain.nodes.research_orchestrator import research_orchestrator
from infrastructure.rag.evaluation import evaluate_itinerary_with_llm_judge
from tests.golden_prompt_replay import load_golden_cases

RUN_LLM_JUDGE_GOLDENS = os.getenv("RUN_LLM_JUDGE_GOLDENS", "").lower() in {"1", "true", "yes"}
GOLDEN_JUDGE_PROVIDER = os.getenv("GOLDEN_JUDGE_PROVIDER", "openai")
GOLDEN_JUDGE_MODEL = os.getenv("GOLDEN_JUDGE_MODEL", "")


@pytest.mark.parametrize("case", load_golden_cases("intake.json"), ids=lambda case: case["id"])
def test_trip_intake_golden(case, mock_llm_responses):
    with mock_llm_responses("domain.nodes.trip_intake", case["responses"]):
        result = trip_intake(case["input_state"])

    expected = case["expected"]
    assert result["current_step"] == expected["current_step"]

    for fragment in expected.get("messages_contains", []):
        assert fragment in result["messages"][0]["content"]

    assert [item["node"] for item in result["token_usage"]] == expected["token_usage_nodes"]

    trip_request = result.get("trip_request", {})
    if trip_request:
        assert trip_request["destination"] == expected["destination"]
        assert trip_request["origin"] == expected["origin"]
        assert trip_request["departure_date"] == expected["departure_date"]
        assert trip_request["return_date"] == expected["return_date"]
        assert trip_request["budget_limit"] == expected["budget_limit"]
        assert trip_request["interests"] == expected["interests"]
        assert trip_request["pace"] == expected["pace"]


@pytest.mark.parametrize("case", load_golden_cases("finaliser.json"), ids=lambda case: case["id"])
def test_trip_finaliser_golden(case, mock_llm_responses):
    with (
        mock_llm_responses("domain.nodes.trip_finaliser", case["responses"]),
        patch("domain.nodes.trip_finaliser.fetch_weather_for_trip", return_value={}),
    ):
        result = trip_finaliser(case["input_state"])

    expected = case["expected"]
    assert result["current_step"] == expected["current_step"]
    assert result["finaliser_metadata"]["used_fallback"] is expected["used_fallback"]

    itinerary_data = result["itinerary_data"]
    first_activity = itinerary_data["daily_plans"][0]["activities"][0]
    assert first_activity["name"] == expected["first_activity_name"]
    assert first_activity["category"] == expected["first_activity_category"]
    assert len(itinerary_data["sources"]) == expected["sources_count"]

    if "first_activity_maps_url" in expected:
        assert first_activity["maps_url"] == expected["first_activity_maps_url"]

    for heading in expected["itinerary_sections"]:
        assert heading in result["final_itinerary"]

    if "leg_count" in expected:
        assert len(itinerary_data["legs"]) == expected["leg_count"]
        assert itinerary_data["legs"][0]["destination"] == expected["first_leg_destination"]
    else:
        assert len(itinerary_data["daily_plans"]) == expected["daily_plan_count"]

    if RUN_LLM_JUDGE_GOLDENS and "judge_thresholds" in expected:
        judge_provider = GOLDEN_JUDGE_PROVIDER or case["input_state"].get("llm_provider", "openai")
        judge_model = GOLDEN_JUDGE_MODEL or ""
        if not judge_model:
            judge_model = "gpt-4.1-mini" if judge_provider == "openai" else "gemini-2.5-flash"

        judge_result = evaluate_itinerary_with_llm_judge(
            input_state=case["input_state"],
            final_itinerary=result["final_itinerary"],
            itinerary_data=itinerary_data,
            provider=judge_provider,
            model=judge_model,
        )["result"]

        for key, minimum in expected["judge_thresholds"].items():
            assert judge_result[key] >= minimum, (
                f"Judge score for {key} was {judge_result[key]}, expected at least {minimum}. "
                f"Judge rationale: {judge_result['rationale']}"
            )
        assert judge_result["pass"] is True, (
            f"Itinerary judge did not pass the case. Issues: {judge_result['issues']}"
        )


@pytest.mark.parametrize("case", load_golden_cases("research.json"), ids=lambda case: case["id"])
def test_research_orchestrator_golden(case, mock_llm_responses):
    tool_results = case["tool_results"]
    input_state = case["input_state"]

    retrieve_side_effect = tool_results.get("retrieve")
    if retrieve_side_effect and isinstance(retrieve_side_effect, list) and retrieve_side_effect:
        if isinstance(retrieve_side_effect[0], dict):
            retrieve_side_effect = [retrieve_side_effect]
    search_leg_flights_side_effect = tool_results.get("search_leg_flights")
    search_leg_hotels_side_effect = tool_results.get("search_leg_hotels")

    with (
        mock_llm_responses("domain.nodes.research_orchestrator", case.get("responses", [])),
        patch(
            "domain.nodes.research_orchestrator.search_flights",
            return_value=tool_results.get("search_flights"),
        ),
        patch(
            "domain.nodes.research_orchestrator.search_hotels",
            return_value=tool_results.get("search_hotels"),
        ),
        patch(
            "domain.nodes.research_orchestrator.search_leg_flights",
            side_effect=search_leg_flights_side_effect,
        ),
        patch(
            "domain.nodes.research_orchestrator.search_leg_hotels",
            side_effect=search_leg_hotels_side_effect,
        ),
        patch(
            "domain.nodes.research_orchestrator.retrieve",
            side_effect=retrieve_side_effect,
        ),
        patch(
            "domain.nodes.research_orchestrator.resolve_destination_country",
            side_effect=lambda destination: {
                "Lisbon": "Portugal",
                "Paris": "France",
                "Barcelona": "Spain",
            }.get(destination, ""),
        ),
        patch("domain.nodes.research_orchestrator.list_place_aliases", return_value=[]),
    ):
        result = research_orchestrator(input_state)

    expected = case["expected"]
    assert result["current_step"] == expected["current_step"]

    for fragment in expected["summary_contains"]:
        assert fragment in result["messages"][0]["content"]
    for fragment in expected["destination_info_contains"]:
        assert fragment in result["destination_info"]

    assert result["rag_sources"] == expected["rag_sources"]
    assert result["rag_trace"][0]["node"] == expected["rag_trace_node"]

    if "token_usage_nodes" in expected:
        assert [item["node"] for item in result["token_usage"]] == expected["token_usage_nodes"]
        assert len(result["flight_options"]) == expected["flight_count"]
        assert len(result["hotel_options"]) == expected["hotel_count"]
    else:
        assert len(result["flight_options_by_leg"]) == expected["flight_options_by_leg_count"]
        assert len(result["hotel_options_by_leg"]) == expected["hotel_options_by_leg_count"]
