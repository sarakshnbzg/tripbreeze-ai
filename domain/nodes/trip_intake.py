"""Trip Intake node — builds trip request from structured form fields
and/or a free-text query, using LLM tool calling to parse user input."""

import re
from datetime import date, timedelta
from typing import Any

from langgraph.types import interrupt

from domain.nodes.trip_intake_schemas import (
    ExtractPreferences,
    ExtractTripDetails,
    ExtractMultiCityTrip,
    EvaluateDomain,
    PREFERENCES_PROMPT,
    FREE_TEXT_PROMPT,
    CLARIFICATION_PROMPT,
    DOMAIN_GUARDRAIL_PROMPT,
)
from domain.nodes.trip_intake_helpers import (
    _apply_clarification_duration_fallback,
    _apply_clarification_intent_fallback,
    _apply_profile_defaults,
    _build_clarification_question,
    _build_trip_legs,
    _build_trip_legs_from_form,
    _build_trip_intake_message,
    _fill_origin_from_profile_if_only_gap,
    _finalise_inferred_multi_city_trip,
    _has_structured_trip_signal,
    _infer_multi_city_data,
    _infer_stay_length_days,
    _infer_missing_dates_from_query,
    _merge_clarification_answer,
    _merge_has_value,
    _merge_single_city_parsed_query,
    _missing_required_fields,
    _normalise_hotel_stars,
    _normalise_trip_data,
    _repair_invalid_duration_dates,
    _recover_multi_city_trip,
)
from application.state import TravelState
from application.workflow_types import WorkflowStep
from domain.utils.sanitize import sanitise_untrusted_text
from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def _classify_domain(llm, query: str, model: str) -> tuple[dict[str, Any], dict | None]:
    """Use LLM tool calling to classify whether a request belongs to the travel domain."""
    if not query.strip():
        return {"in_domain": True, "reason": ""}, None

    sanitised_query = sanitise_untrusted_text(query)
    logger.info("Classifying request domain via LLM: %s", sanitised_query)
    llm_with_tools = llm.bind_tools([EvaluateDomain])
    response = invoke_with_retry(
        llm_with_tools,
        f"{DOMAIN_GUARDRAIL_PROMPT}\n\n<user_query>\n{sanitised_query}\n</user_query>",
    )

    usage = extract_token_usage(response, model=model, node="domain_guardrail")

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Domain guardrail returned no tool calls")
        return {"in_domain": True, "reason": ""}, usage

    return tool_calls[0].get("args", {}), usage


def _parse_free_text(llm, query: str, model: str) -> tuple[dict[str, Any], bool, dict | None]:
    """Use LLM tool calling to extract trip details from a free-text query.

    Returns (parsed_args, is_multi_city, token_usage_dict).
    The LLM chooses between ExtractTripDetails (single destination) and
    ExtractMultiCityTrip (multiple destinations) based on the query.
    """
    if not query.strip():
        return {}, False, None

    sanitised_query = sanitise_untrusted_text(query)
    logger.info("Parsing free-text query via LLM: %s", sanitised_query)
    llm_with_tools = llm.bind_tools([ExtractTripDetails, ExtractMultiCityTrip])
    prompt = FREE_TEXT_PROMPT.format(today=date.today().isoformat())
    response = invoke_with_retry(
        llm_with_tools,
        f"{prompt}\n\n<user_query>\n{sanitised_query}\n</user_query>",
    )

    usage = extract_token_usage(response, model=model, node="trip_intake")

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Free-text extraction returned no tool calls")
        return {}, False, usage

    tool_call = tool_calls[0]
    tool_name = tool_call.get("name", "")
    is_multi_city = tool_name == "ExtractMultiCityTrip"
    logger.info("Free-text extraction used tool: %s (multi_city=%s)", tool_name, is_multi_city)

    return tool_call.get("args", {}), is_multi_city, usage

def _parse_clarification(
    llm,
    answer: str,
    missing_fields: list[str],
    question: str,
    original_query: str,
    raw_trip_data: dict[str, Any],
    prefer_multi_city: bool,
    model: str,
) -> tuple[dict[str, Any], bool, dict | None]:
    """Parse a clarification answer, telling the LLM which fields it is filling.

    Without this hint, a bare answer like "Berlin" tends to be extracted as
    `destination` (and silently dropped if destination was already set),
    causing the clarification loop to ask the same question forever.
    """
    if not answer.strip():
        return {}, False, None

    sanitised_answer = sanitise_untrusted_text(answer)
    sanitised_original_query = sanitise_untrusted_text(original_query)
    logger.info(
        "Parsing clarification via LLM: fields=%s multi_city=%s answer=%s",
        missing_fields,
        prefer_multi_city,
        sanitised_answer,
    )
    llm_with_tools = llm.bind_tools([ExtractTripDetails, ExtractMultiCityTrip])
    prompt = (
        f"{CLARIFICATION_PROMPT.format(today=date.today().isoformat())}\n\n"
        f"<trip_mode>\n{'multi_city' if prefer_multi_city else 'single_destination'}\n</trip_mode>\n"
        f"<original_request>\n{sanitised_original_query}\n</original_request>\n"
        f"<current_trip_state>\n{raw_trip_data}\n</current_trip_state>\n"
        f"<clarification_question>\n{question}\n</clarification_question>\n"
        f"<target_fields>\n{', '.join(missing_fields)}\n</target_fields>\n"
        f"<user_answer>\n{sanitised_answer}\n</user_answer>"
    )
    response = invoke_with_retry(llm_with_tools, prompt)

    usage = extract_token_usage(response, model=model, node="trip_intake")

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Clarification extraction returned no tool calls")
        return {}, False, usage

    tool_call = tool_calls[0]
    tool_name = tool_call.get("name", "")
    is_multi_city = tool_name == "ExtractMultiCityTrip"
    parsed = tool_call.get("args", {}) or {}

    allowed_fields = set(missing_fields)
    if is_multi_city:
        allowed_fields.update({"legs", "return_to_origin"})

    filtered = {k: v for k, v in parsed.items() if k in allowed_fields}
    return filtered, is_multi_city, usage

def _parse_preferences(llm, preferences: str, model: str) -> tuple[dict[str, Any], dict | None]:
    """Use LLM tool calling to extract structured filters from free-text preferences.

    Returns (parsed_args, token_usage_dict).
    """
    if not preferences.strip():
        return {}, None

    sanitised_preferences = sanitise_untrusted_text(preferences)
    logger.info("Parsing preferences via LLM: %s", sanitised_preferences)
    llm_with_tools = llm.bind_tools([ExtractPreferences])
    response = invoke_with_retry(
        llm_with_tools,
        f"{PREFERENCES_PROMPT}\n\n<user_preferences>\n{sanitised_preferences}\n</user_preferences>",
    )

    usage = extract_token_usage(response, model=model, node="trip_intake")

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Preferences extraction returned no tool calls")
        return {}, usage

    return tool_calls[0].get("args", {}), usage


def _conflict_value_text(field: str, value: Any) -> str:
    if field in {"travel_class"}:
        return str(value or "").replace("_", " ").title() or "not set"
    if field in {"include_airlines", "exclude_airlines"}:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if str(item).strip()) or "none"
    if field == "stops":
        if value == 0:
            return "direct only"
        if isinstance(value, int):
            return f"up to {value} stop{'s' if value != 1 else ''}"
    if field == "max_duration":
        try:
            total = int(value)
        except (TypeError, ValueError):
            return str(value or "not set")
        hours, minutes = divmod(total, 60)
        if hours and minutes:
            return f"{hours}h {minutes}m"
        if hours:
            return f"{hours}h"
        if minutes:
            return f"{minutes}m"
        return "not set"
    if field == "legs" and isinstance(value, list):
        return " then ".join(
            f"{leg.get('destination', '?')} for {leg.get('nights', '?')} nights"
            for leg in value
        ) or "not set"
    if field == "return_to_origin":
        return "return to origin" if value else "open-jaw / one-way"
    return str(value or "not set")


def _build_conflict_question(field: str, structured_value: Any, parsed_value: Any, is_multi_city: bool) -> str:
    structured_text = _conflict_value_text(field, structured_value)
    parsed_text = _conflict_value_text(field, parsed_value)

    if field == "travel_class":
        return (
            f"Your typed request says {parsed_text}, but the refine fields say {structured_text}. "
            "Which cabin class should I use?"
        )
    if field in {"origin", "destination"}:
        label = "origin" if field == "origin" else "destination"
        return (
            f"Your typed request says {parsed_text} for the {label}, but the refine fields say {structured_text}. "
            f"Which {label} should I use?"
        )
    if field in {"departure_date", "return_date"}:
        label = "departure date" if field == "departure_date" else "return date"
        return (
            f"Your typed request says {parsed_text} for the {label}, but the refine fields say {structured_text}. "
            f"Which {label} should I use?"
        )
    if field == "is_one_way":
        return (
            f"Your typed request implies {parsed_text}, but the refine fields say {structured_text}. "
            "Should I treat this as one-way or round-trip?"
        )
    if field == "stops":
        return (
            f"Your typed request says {parsed_text}, but the refine fields say {structured_text}. "
            "Which stop preference should I use?"
        )
    if field == "max_duration":
        return (
            f"Your typed request says a max flight duration of {parsed_text}, but the refine fields say {structured_text}. "
            "What maximum flight duration should I use?"
        )
    if field in {"include_airlines", "exclude_airlines"}:
        action = "include" if field == "include_airlines" else "exclude"
        return (
            f"Your typed request says to {action} {parsed_text}, but the refine fields say {structured_text}. "
            f"Which airlines should I {action}?"
        )
    if field == "legs" and is_multi_city:
        return (
            f"Your typed request describes {parsed_text}, but the refine fields describe {structured_text}. "
            "Which destinations and nights should I use?"
        )
    if field == "return_to_origin" and is_multi_city:
        return (
            f"Your typed request implies {parsed_text}, but the refine fields say {structured_text}. "
            "Should I return to the origin city at the end of the trip?"
        )
    return (
        f"Your typed request says {parsed_text}, but the refine fields say {structured_text}. "
        f"Which {field.replace('_', ' ')} should I use?"
    )


def _find_conflicting_field(
    structured_fields: dict[str, Any],
    parsed_query: dict[str, Any],
    *,
    is_multi_city: bool,
    resolved_fields: set[str],
) -> tuple[str, Any, Any] | None:
    conflict_pairs: list[tuple[str, str]] = [
        ("origin", "origin"),
        ("destination", "destination"),
        ("departure_date", "departure_date"),
        ("return_date", "return_date"),
        ("is_one_way", "is_one_way"),
        ("travel_class", "travel_class"),
        ("stops", "stops"),
        ("max_duration", "max_duration"),
        ("include_airlines", "include_airlines"),
        ("exclude_airlines", "exclude_airlines"),
    ]

    for field, parsed_key in conflict_pairs:
        if field in resolved_fields or parsed_key in resolved_fields:
            continue
        structured_value = structured_fields.get(field)
        parsed_value = parsed_query.get(parsed_key)
        if not _merge_has_value(field, structured_value) or not _merge_has_value(parsed_key, parsed_value):
            continue
        if structured_value != parsed_value:
            return parsed_key, structured_value, parsed_value

    if is_multi_city:
        if "legs" not in resolved_fields and structured_fields.get("multi_city_legs") and parsed_query.get("legs"):
            structured_legs = [
                {"destination": leg.get("destination"), "nights": leg.get("nights")}
                for leg in structured_fields.get("multi_city_legs", [])
            ]
            parsed_legs = [
                {"destination": leg.get("destination"), "nights": leg.get("nights")}
                for leg in parsed_query.get("legs", [])
            ]
            if structured_legs and parsed_legs and structured_legs != parsed_legs:
                return "legs", structured_legs, parsed_legs
        if "return_to_origin" not in resolved_fields:
            structured_return = structured_fields.get("return_to_origin")
            parsed_return = parsed_query.get("return_to_origin")
            if structured_return is not None and parsed_return is not None and structured_return != parsed_return:
                return "return_to_origin", structured_return, parsed_return

    return None


def _remove_implicit_profile_origin(
    structured_fields: dict[str, Any],
    profile: dict[str, Any],
    *,
    free_text_query: str,
    revision_mode: bool,
) -> dict[str, Any]:
    """Drop a profile-prefilled origin so typed free text can speak for itself."""
    effective_fields = dict(structured_fields)
    if revision_mode or not free_text_query.strip():
        return effective_fields

    profile_home_city = str(profile.get("home_city") or "").strip()
    structured_origin = str(effective_fields.get("origin") or "").strip()
    if profile_home_city and structured_origin and structured_origin.casefold() == profile_home_city.casefold():
        effective_fields.pop("origin", None)

    return effective_fields


def trip_intake(state: TravelState) -> dict:
    """LangGraph node: build trip request from structured form fields and/or free text."""
    profile = state.get("user_profile", {})
    structured_fields = state.get("structured_fields", {})
    revision_baseline = state.get("revision_baseline", {})
    free_text_query = state.get("free_text_query", "")
    revision_mode = bool(revision_baseline)
    effective_structured_fields = _remove_implicit_profile_origin(
        structured_fields,
        profile,
        free_text_query=free_text_query,
        revision_mode=revision_mode,
    )

    token_usage: list[dict] = []
    model = state.get("llm_model")
    provider = state.get("llm_provider")
    temperature = float(state.get("llm_temperature", 0))

    # Start with structured fields as the base
    raw_trip_data = dict(revision_baseline or effective_structured_fields)

    has_structured_trip_signal = _has_structured_trip_signal(effective_structured_fields)

    if free_text_query.strip() and not revision_mode and not has_structured_trip_signal:
        llm = create_chat_model(provider, model, temperature=temperature)
        domain_result, usage = _classify_domain(llm, free_text_query, model=model)
        if usage:
            token_usage.append(usage)
        if not domain_result.get("in_domain", True):
            logger.info(
                "Trip intake stopped because LLM classified request as out of domain: %s",
                domain_result.get("reason", ""),
            )
            log_event(
                logger,
                "workflow.intake_blocked_out_of_domain",
                reason=domain_result.get("reason", ""),
            )
            return {
                "error": "Out-of-domain request.",
                "current_step": WorkflowStep.OUT_OF_DOMAIN,
                "token_usage": token_usage,
                "messages": [
                    {
                        "role": "assistant",
                        "content": (
                            "I can help with travel planning only, like trips, flights, hotels, "
                            "destinations, budgets, and itinerary questions. Please send a travel-related request."
                        ),
                    }
                ],
            }

    # If there's a free-text query, extract trip details from it
    is_multi_city = False
    trip_legs: list[dict[str, Any]] = []
    inferred_multi_city_data: dict[str, Any] | None = None
    parsed_query_for_conflicts: dict[str, Any] = {}

    # Check for multi-city from structured form fields first
    if effective_structured_fields.get("multi_city_legs"):
        try:
            trip_legs, trip_updates = _build_trip_legs_from_form(effective_structured_fields, profile)
            if trip_legs:
                is_multi_city = True
                raw_trip_data.update(trip_updates)
                logger.info("Multi-city trip from form with %d legs", len(trip_legs))
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to build trip legs from form: %s", exc)

    # If there's a free-text query and no multi-city from form, extract trip details
    if free_text_query.strip() and not trip_legs:
        logger.info("Trip intake parsing free-text query")
        llm = create_chat_model(provider, model, temperature=temperature)
        parsed_query, is_multi_city, usage = _parse_free_text(llm, free_text_query, model=model)
        parsed_query_for_conflicts = parsed_query or {}
        if usage:
            token_usage.append(usage)

        if is_multi_city:
            inferred_multi_city_data = parsed_query
            if not _merge_has_value("origin", raw_trip_data.get("origin")) and _merge_has_value("origin", parsed_query.get("origin")):
                raw_trip_data["origin"] = parsed_query["origin"]
            if not _merge_has_value("destination", raw_trip_data.get("destination")) and parsed_query.get("legs"):
                raw_trip_data["destination"] = parsed_query["legs"][0].get("destination", "")
            for key in (
                "num_travelers", "budget_limit", "currency", "preferences",
                "stops", "max_flight_price", "max_duration", "bags", "emissions",
                "layover_duration_min", "layover_duration_max",
                "include_airlines", "exclude_airlines",
                "hotel_stars", "travel_class", "interests", "pace",
            ):
                if _merge_has_value(key, parsed_query.get(key)) and not _merge_has_value(key, raw_trip_data.get(key)):
                    raw_trip_data[key] = parsed_query[key]
            # Multi-city trip: build legs and derive trip_request from them
            trip_legs = _build_trip_legs(parsed_query, raw_trip_data.get("origin", ""), profile)
            if trip_legs:
                # Populate raw_trip_data from multi-city extraction for normalization
                raw_trip_data["origin"] = trip_legs[0]["origin"]
                raw_trip_data["destination"] = trip_legs[0]["destination"]  # First destination
                raw_trip_data["departure_date"] = trip_legs[0]["departure_date"]
                # Return date is the departure date of the last leg (return flight)
                raw_trip_data["return_date"] = trip_legs[-1]["departure_date"]
                logger.info("Multi-city trip with %d legs detected", len(trip_legs))
        else:
            _merge_single_city_parsed_query(
                raw_trip_data,
                parsed_query,
                revision_mode=revision_mode,
            )
            trip_legs, inferred_multi_city_data = _recover_multi_city_trip(
                raw_trip_data,
                free_text_query,
                profile,
            )
            if trip_legs:
                is_multi_city = True
    else:
        logger.info("Trip intake using structured fields only")

    _infer_missing_dates_from_query(raw_trip_data, free_text_query)

    if (
        raw_trip_data.get("departure_date")
        and raw_trip_data.get("check_out_date")
        and not raw_trip_data.get("return_date")
        and not raw_trip_data.get("is_one_way")
    ):
        raw_trip_data["return_date"] = raw_trip_data["check_out_date"]

    # If the saved home city is the only remaining gap, use it directly.
    # When other required fields are also missing, prefer asking the user so
    # they can confirm origin and dates together in the clarification step.
    _fill_origin_from_profile_if_only_gap(raw_trip_data, profile)

    # ── Check for missing required fields and ask the user ──
    # Ask for clarification whenever a free-text search still lacks required trip
    # fields after merging parsed text and structured inputs. This keeps mixed-mode
    # searches working even when the form contributes defaults like currency or
    # travel class that should not suppress follow-up questions.
    #
    # Uses a loop so that if the user's answer still leaves gaps, we ask again.
    # LangGraph replays answered interrupts on re-run, so each iteration's
    # interrupt() returns the previously supplied answer automatically.
    if free_text_query.strip() and not revision_mode:
        resolved_conflict_fields: set[str] = set()
        while True:
            conflict = _find_conflicting_field(
                effective_structured_fields,
                parsed_query_for_conflicts,
                is_multi_city=bool(trip_legs or inferred_multi_city_data),
                resolved_fields=resolved_conflict_fields,
            )
            if conflict:
                conflict_field, structured_value, parsed_value = conflict
                target_fields = [conflict_field]
                question = _build_conflict_question(
                    conflict_field,
                    structured_value,
                    parsed_value,
                    bool(trip_legs or inferred_multi_city_data),
                )
                logger.info("Conflict on field %s — interrupting for clarification", conflict_field)
                log_event(
                    logger,
                    "workflow.intake_conflict_clarification_requested",
                    field=conflict_field,
                    is_multi_city=bool(trip_legs),
                )
                try:
                    clarification_answer = interrupt({
                        "type": "clarification",
                        "question": question,
                        "missing_fields": target_fields,
                        "conflict_field": conflict_field,
                    })
                except RuntimeError as exc:
                    if "outside of a runnable context" not in str(exc):
                        raise
                    logger.info(
                        "Skipping conflict clarification outside runnable context; proceeding with precedence rules"
                    )
                    break
                if not clarification_answer:
                    break
                logger.info("Conflict clarification answer received: %s", clarification_answer)
                llm = create_chat_model(provider, model, temperature=temperature)
                parsed_answer, clarification_is_multi_city, usage = _parse_clarification(
                    llm,
                    clarification_answer,
                    target_fields,
                    question,
                    free_text_query,
                    raw_trip_data,
                    bool(trip_legs or inferred_multi_city_data or effective_structured_fields.get("multi_city_legs")),
                    model=model,
                )
                parsed_answer = _apply_clarification_duration_fallback(
                    parsed_answer,
                    clarification_answer,
                    raw_trip_data,
                    target_fields,
                )
                parsed_answer = _apply_clarification_intent_fallback(
                    parsed_answer,
                    clarification_answer,
                    target_fields,
                )
                if usage:
                    token_usage.append(usage)
                if clarification_is_multi_city:
                    inferred_multi_city_data = inferred_multi_city_data or {}
                inferred_multi_city_data = _merge_clarification_answer(
                    raw_trip_data,
                    parsed_answer,
                    inferred_multi_city_data,
                    override_fields=set(target_fields),
                )
                _repair_invalid_duration_dates(
                    raw_trip_data,
                    free_text_query,
                    parsed_answer,
                    target_fields,
                )
                resolved_conflict_fields.update(target_fields)
                continue

            missing_fields = _missing_required_fields(raw_trip_data)

            if not missing_fields:
                break

            question = _build_clarification_question(missing_fields, profile)
            logger.info("Missing fields %s — interrupting for clarification", missing_fields)
            log_event(
                logger,
                "workflow.intake_clarification_requested",
                missing_fields=missing_fields,
                is_multi_city=bool(trip_legs),
            )
            try:
                clarification_answer = interrupt({
                    "type": "clarification",
                    "question": question,
                    "missing_fields": missing_fields,
                })
            except RuntimeError as exc:
                if "outside of a runnable context" not in str(exc):
                    raise
                logger.info(
                    "Skipping clarification interrupt outside runnable context; proceeding with partial trip data"
                )
                break
            # On resume: parse the user's answer and merge into raw_trip_data
            if not clarification_answer:
                break  # empty answer — proceed with what we have
            logger.info("Clarification answer received: %s", clarification_answer)
            llm = create_chat_model(provider, model, temperature=temperature)
            parsed_answer, clarification_is_multi_city, usage = _parse_clarification(
                llm,
                clarification_answer,
                missing_fields,
                question,
                free_text_query,
                raw_trip_data,
                bool(trip_legs or inferred_multi_city_data or structured_fields.get("multi_city_legs")),
                model=model,
            )
            parsed_answer = _apply_clarification_duration_fallback(
                parsed_answer,
                clarification_answer,
                raw_trip_data,
                missing_fields,
            )
            parsed_answer = _apply_clarification_intent_fallback(
                parsed_answer,
                clarification_answer,
                missing_fields,
            )
            if usage:
                token_usage.append(usage)
            if clarification_is_multi_city:
                inferred_multi_city_data = inferred_multi_city_data or {}
            inferred_multi_city_data = _merge_clarification_answer(
                raw_trip_data,
                parsed_answer,
                inferred_multi_city_data,
                override_fields=set(missing_fields),
            )
            _repair_invalid_duration_dates(
                raw_trip_data,
                free_text_query,
                parsed_answer,
                missing_fields,
            )

    if inferred_multi_city_data and not trip_legs and raw_trip_data.get("departure_date"):
        trip_legs = _finalise_inferred_multi_city_trip(raw_trip_data, inferred_multi_city_data, profile)
        if trip_legs:
            is_multi_city = True

    _apply_profile_defaults(raw_trip_data, profile)

    # Parse explicit structured special requests into filter criteria, including
    # when a main free-text trip prompt is also present. Preferences synthesized
    # by the free-text trip parser should not trigger an extra LLM call here.
    structured_preferences = str(structured_fields.get("preferences") or "").strip()
    preferences = raw_trip_data.get("preferences", "")
    if structured_preferences and str(preferences).strip():
        llm = create_chat_model(provider, model, temperature=temperature)
        parsed, usage = _parse_preferences(llm, preferences, model=model)
        if usage:
            token_usage.append(usage)
        for key in (
            "stops", "max_flight_price", "max_duration", "bags", "emissions",
            "layover_duration_min", "layover_duration_max",
            "include_airlines", "exclude_airlines",
            "hotel_stars", "travel_class",
            "interests", "pace",
        ):
            value = parsed.get(key)
            if _merge_has_value(key, value) and not _merge_has_value(key, raw_trip_data.get(key)):
                raw_trip_data[key] = value

    try:
        trip_data = _normalise_trip_data(raw_trip_data, profile)
    except ValueError as exc:
        logger.warning("Trip intake validation error: %s", exc)
        log_event(logger, "workflow.intake_failed", reason="validation_error", error=str(exc))
        return {
            "error": str(exc),
            "current_step": WorkflowStep.INTAKE_ERROR,
            "messages": [{"role": "assistant", "content": f"I couldn't process your trip details: {exc}"}],
        }
    except Exception as exc:
        logger.exception("Trip intake failed during normalisation")
        log_event(logger, "workflow.intake_failed", reason="normalisation_exception", error=str(exc))
        return {
            "error": "Something went wrong while processing your trip details. Please try again.",
            "current_step": WorkflowStep.INTAKE_ERROR,
            "messages": [{"role": "assistant", "content": "Something went wrong while processing your trip details. Please try again."}],
        }

    logger.info(
        "Trip intake complete origin=%s destination=%s departure=%s return=%s travelers=%s multi_city=%s",
        trip_data.get("origin"),
        trip_data.get("destination"),
        trip_data.get("departure_date"),
        trip_data.get("return_date"),
        trip_data.get("num_travelers"),
        bool(trip_legs),
    )
    log_event(
        logger,
        "workflow.intake_completed",
        origin=trip_data.get("origin"),
        destination=trip_data.get("destination"),
        departure_date=trip_data.get("departure_date"),
        has_return_date=bool(trip_data.get("return_date")),
        traveler_count=trip_data.get("num_travelers"),
        is_multi_city=bool(trip_legs),
        trip_leg_count=len(trip_legs),
    )

    return {
        "trip_request": trip_data,
        "trip_legs": trip_legs,
        "token_usage": token_usage,
        "messages": [{"role": "assistant", "content": _build_trip_intake_message(trip_data, trip_legs)}],
        "current_step": WorkflowStep.INTAKE_COMPLETE,
    }
