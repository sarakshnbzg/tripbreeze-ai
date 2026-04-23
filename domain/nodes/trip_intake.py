"""Trip Intake node — builds trip request from structured form fields
and/or a free-text query, using LLM tool calling to parse user input."""

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
    _has_structured_trip_signal,
    _infer_multi_city_data,
    _infer_stay_length_days,
    _merge_has_value,
    _normalise_hotel_stars,
    _normalise_trip_data,
    _repair_invalid_duration_dates,
)
from infrastructure.currency_utils import format_currency
from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

def _classify_domain(llm, query: str, model: str) -> tuple[dict[str, Any], dict | None]:
    """Use LLM tool calling to classify whether a request belongs to the travel domain."""
    if not query.strip():
        return {"in_domain": True, "reason": ""}, None

    logger.info("Classifying request domain via LLM: %s", query)
    llm_with_tools = llm.bind_tools([EvaluateDomain])
    response = invoke_with_retry(
        llm_with_tools,
        f"{DOMAIN_GUARDRAIL_PROMPT}\n\n<user_query>\n{query}\n</user_query>",
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

    logger.info("Parsing free-text query via LLM: %s", query)
    llm_with_tools = llm.bind_tools([ExtractTripDetails, ExtractMultiCityTrip])
    prompt = FREE_TEXT_PROMPT.format(today=date.today().isoformat())
    response = invoke_with_retry(
        llm_with_tools,
        f"{prompt}\n\n<user_query>\n{query}\n</user_query>",
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

    logger.info(
        "Parsing clarification via LLM: fields=%s multi_city=%s answer=%s",
        missing_fields,
        prefer_multi_city,
        answer,
    )
    llm_with_tools = llm.bind_tools([ExtractTripDetails, ExtractMultiCityTrip])
    prompt = (
        f"{CLARIFICATION_PROMPT.format(today=date.today().isoformat())}\n\n"
        f"<trip_mode>\n{'multi_city' if prefer_multi_city else 'single_destination'}\n</trip_mode>\n"
        f"<original_request>\n{original_query}\n</original_request>\n"
        f"<current_trip_state>\n{raw_trip_data}\n</current_trip_state>\n"
        f"<clarification_question>\n{question}\n</clarification_question>\n"
        f"<target_fields>\n{', '.join(missing_fields)}\n</target_fields>\n"
        f"<user_answer>\n{answer}\n</user_answer>"
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

    logger.info("Parsing preferences via LLM: %s", preferences)
    llm_with_tools = llm.bind_tools([ExtractPreferences])
    response = invoke_with_retry(
        llm_with_tools,
        f"{PREFERENCES_PROMPT}\n\n<user_preferences>\n{preferences}\n</user_preferences>",
    )

    usage = extract_token_usage(response, model=model, node="trip_intake")

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Preferences extraction returned no tool calls")
        return {}, usage

    return tool_calls[0].get("args", {}), usage

def trip_intake(state: dict) -> dict:
    """LangGraph node: build trip request from structured form fields and/or free text."""
    profile = state.get("user_profile", {})
    structured_fields = state.get("structured_fields", {})
    revision_baseline = state.get("revision_baseline", {})
    free_text_query = state.get("free_text_query", "")
    revision_mode = bool(revision_baseline)

    token_usage: list[dict] = []
    model = state.get("llm_model")
    provider = state.get("llm_provider")
    temperature = float(state.get("llm_temperature", 0))

    # Start with structured fields as the base
    raw_trip_data = dict(revision_baseline or structured_fields)

    has_structured_trip_signal = _has_structured_trip_signal(structured_fields)

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
            return {
                "error": "Out-of-domain request.",
                "current_step": "out_of_domain",
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

    # Check for multi-city from structured form fields first
    if structured_fields.get("multi_city_legs"):
        form_legs = structured_fields["multi_city_legs"]
        origin = structured_fields.get("origin") or profile.get("home_city") or ""
        departure_date_str = structured_fields.get("departure_date", "")
        return_to_origin = structured_fields.get("return_to_origin", True)

        if origin and departure_date_str and form_legs:
            try:
                current_date = date.fromisoformat(departure_date_str)
                current_city = origin
                for leg_data in form_legs:
                    dest = leg_data.get("destination", "")
                    nights = leg_data.get("nights", 0)
                    if not dest:
                        continue
                    check_out = (current_date + timedelta(days=nights)).isoformat() if nights > 0 else None
                    trip_legs.append({
                        "leg_index": len(trip_legs),
                        "origin": current_city,
                        "destination": dest,
                        "departure_date": current_date.isoformat(),
                        "nights": nights,
                        "needs_hotel": nights > 0,
                        "check_out_date": check_out,
                    })
                    current_city = dest
                    current_date = current_date + timedelta(days=nights)

                # Add return leg (skip for open-jaw / one-way multi-city)
                if return_to_origin and current_city != origin:
                    trip_legs.append({
                        "leg_index": len(trip_legs),
                        "origin": current_city,
                        "destination": origin,
                        "departure_date": current_date.isoformat(),
                        "nights": 0,
                        "needs_hotel": False,
                        "check_out_date": None,
                    })

                if trip_legs:
                    is_multi_city = True
                    raw_trip_data["origin"] = trip_legs[0]["origin"]
                    raw_trip_data["destination"] = trip_legs[0]["destination"]
                    raw_trip_data["departure_date"] = trip_legs[0]["departure_date"]
                    raw_trip_data["return_date"] = trip_legs[-1]["departure_date"]
                    logger.info("Multi-city trip from form with %d legs", len(trip_legs))
            except (ValueError, TypeError) as exc:
                logger.warning("Failed to build trip legs from form: %s", exc)

    # If there's a free-text query and no multi-city from form, extract trip details
    if free_text_query.strip() and not trip_legs:
        logger.info("Trip intake parsing free-text query")
        llm = create_chat_model(provider, model, temperature=temperature)
        parsed_query, is_multi_city, usage = _parse_free_text(llm, free_text_query, model=model)
        if usage:
            token_usage.append(usage)

        if is_multi_city:
            inferred_multi_city_data = parsed_query
            if not raw_trip_data.get("origin") and parsed_query.get("origin"):
                raw_trip_data["origin"] = parsed_query["origin"]
            if not raw_trip_data.get("destination") and parsed_query.get("legs"):
                raw_trip_data["destination"] = parsed_query["legs"][0].get("destination", "")
            for key in (
                "num_travelers", "budget_limit", "currency", "preferences",
                "stops", "hotel_stars", "travel_class", "interests", "pace",
            ):
                if parsed_query.get(key) not in (None, "", []):
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
            # Single-destination: merge parsed values into raw_trip_data
            for key, value in parsed_query.items():
                not_empty = value is not None and value != "" and value != [] and (value != 0 or key == "stops")
                already_set = raw_trip_data.get(key) not in (None, "", []) if key != "stops" else raw_trip_data.get(key) is not None
                if not_empty and (revision_mode or not already_set):
                    raw_trip_data[key] = value

            # If the free-text query had extra preferences, append to existing
            if parsed_query.get("preferences"):
                existing_prefs = raw_trip_data.get("preferences", "")
                ft_prefs = parsed_query["preferences"]
                if existing_prefs and ft_prefs not in existing_prefs:
                    raw_trip_data["preferences"] = f"{existing_prefs}, {ft_prefs}"
                elif not existing_prefs:
                    raw_trip_data["preferences"] = ft_prefs

            inferred_multi_city_data = _infer_multi_city_data(free_text_query)
            if inferred_multi_city_data:
                logger.info(
                    "Recovered multi-city structure from free text fallback with %d legs",
                    len(inferred_multi_city_data.get("legs", [])),
                )
                if not raw_trip_data.get("destination") and inferred_multi_city_data.get("legs"):
                    raw_trip_data["destination"] = inferred_multi_city_data["legs"][0]["destination"]
                for key in ("num_travelers", "budget_limit", "currency"):
                    if not _merge_has_value(key, raw_trip_data.get(key)) and _merge_has_value(key, inferred_multi_city_data.get(key)):
                        raw_trip_data[key] = inferred_multi_city_data[key]
                if raw_trip_data.get("departure_date"):
                    multi_city_seed = {
                        **inferred_multi_city_data,
                        "origin": raw_trip_data.get("origin") or "",
                        "departure_date": raw_trip_data.get("departure_date") or "",
                        "return_to_origin": False if raw_trip_data.get("is_one_way") else inferred_multi_city_data.get("return_to_origin", True),
                    }
                    built_legs = _build_trip_legs(multi_city_seed, raw_trip_data.get("origin", ""), profile)
                    if built_legs:
                        trip_legs = built_legs
                        is_multi_city = True
                        raw_trip_data["origin"] = trip_legs[0]["origin"]
                        raw_trip_data["destination"] = trip_legs[0]["destination"]
                        raw_trip_data["departure_date"] = trip_legs[0]["departure_date"]
                        raw_trip_data["return_date"] = trip_legs[-1]["departure_date"]
    else:
        logger.info("Trip intake using structured fields only")

    if (
        free_text_query.strip()
        and raw_trip_data.get("departure_date")
        and not raw_trip_data.get("return_date")
        and not raw_trip_data.get("check_out_date")
    ):
        inferred_days = _infer_stay_length_days(free_text_query)
        if inferred_days:
            inferred_check_out = (
                date.fromisoformat(raw_trip_data["departure_date"]) + timedelta(days=inferred_days)
            ).isoformat()
            raw_trip_data["check_out_date"] = inferred_check_out
            if not raw_trip_data.get("is_one_way"):
                raw_trip_data["return_date"] = inferred_check_out
            logger.info(
                "Inferred stay length from free text: %s day(s), check_out_date=%s return_date=%s",
                inferred_days,
                inferred_check_out,
                raw_trip_data.get("return_date", ""),
            )

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
    if (
        not raw_trip_data.get("origin")
        and profile.get("home_city")
        and raw_trip_data.get("destination")
        and raw_trip_data.get("departure_date")
        and (
            raw_trip_data.get("return_date")
            or raw_trip_data.get("check_out_date")
            or raw_trip_data.get("is_one_way")
        )
    ):
        raw_trip_data["origin"] = profile["home_city"]

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
        while True:
            missing_fields: list[str] = []
            if not raw_trip_data.get("destination"):
                missing_fields.append("destination")
            if not raw_trip_data.get("origin"):
                missing_fields.append("origin")
            if not raw_trip_data.get("departure_date"):
                missing_fields.append("departure_date")
            if (
                not raw_trip_data.get("return_date")
                and not raw_trip_data.get("check_out_date")
                and not raw_trip_data.get("is_one_way")
            ):
                missing_fields.append("return_date")

            if not missing_fields:
                break

            question = _build_clarification_question(missing_fields, profile)
            logger.info("Missing fields %s — interrupting for clarification", missing_fields)
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
                if inferred_multi_city_data is None:
                    inferred_multi_city_data = {}
                if parsed_answer.get("legs"):
                    inferred_multi_city_data["legs"] = parsed_answer["legs"]
                    if not raw_trip_data.get("destination"):
                        raw_trip_data["destination"] = parsed_answer["legs"][0].get("destination", "")
                if "return_to_origin" in parsed_answer:
                    inferred_multi_city_data["return_to_origin"] = parsed_answer["return_to_origin"]
                    if parsed_answer["return_to_origin"] is False:
                        raw_trip_data["is_one_way"] = True
                        raw_trip_data["return_date"] = ""
            for key, value in parsed_answer.items():
                not_empty = _merge_has_value(key, value) or (key == "return_date" and value == "")
                already_set = _merge_has_value(key, raw_trip_data.get(key))
                if not_empty and not already_set:
                    raw_trip_data[key] = value
            _repair_invalid_duration_dates(
                raw_trip_data,
                free_text_query,
                parsed_answer,
                missing_fields,
            )

    if inferred_multi_city_data and not trip_legs and raw_trip_data.get("departure_date"):
        multi_city_seed = {
            **inferred_multi_city_data,
            "origin": raw_trip_data.get("origin") or "",
            "departure_date": raw_trip_data.get("departure_date") or "",
            "return_to_origin": False if raw_trip_data.get("is_one_way") else inferred_multi_city_data.get("return_to_origin", True),
        }
        trip_legs = _build_trip_legs(multi_city_seed, raw_trip_data.get("origin", ""), profile)
        if trip_legs:
            is_multi_city = True
            raw_trip_data["origin"] = trip_legs[0]["origin"]
            raw_trip_data["destination"] = trip_legs[0]["destination"]
            raw_trip_data["departure_date"] = trip_legs[0]["departure_date"]
            raw_trip_data["return_date"] = trip_legs[-1]["departure_date"]

    _apply_profile_defaults(raw_trip_data, profile)

    # Parse any remaining free-text preferences into filter criteria
    preferences = raw_trip_data.get("preferences", "")
    if preferences.strip() and not free_text_query.strip():
        # Only run separate preferences parsing if we didn't already parse free text
        # (free text parsing already extracts filter criteria)
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
            if value is not None and value != "" and value != []:
                raw_trip_data[key] = value

    try:
        trip_data = _normalise_trip_data(raw_trip_data, profile)
    except ValueError as exc:
        logger.warning("Trip intake validation error: %s", exc)
        return {
            "error": str(exc),
            "current_step": "intake_error",
            "messages": [{"role": "assistant", "content": f"I couldn't process your trip details: {exc}"}],
        }
    except Exception as exc:
        logger.exception("Trip intake failed during normalisation")
        return {
            "error": "Something went wrong while processing your trip details. Please try again.",
            "current_step": "intake_error",
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

    # Build confirmation message
    if trip_legs:
        # Multi-city trip message
        legs_summary = " → ".join(leg["destination"] for leg in trip_legs)
        message_content = (
            f"Got it! Planning a multi-city trip:\n"
            f"📍 {trip_data.get('origin', '?')} → {legs_summary}\n"
            f"📅 {trip_data.get('departure_date', '?')} to {trip_data.get('return_date', '?')}\n"
            f"👥 {trip_data.get('num_travelers', 1)} traveler(s)\n"
            f"💰 Budget: {format_currency(trip_data.get('budget_limit'), trip_data.get('currency')) if trip_data.get('budget_limit') else 'flexible'}\n\n"
            "Searching for flights, hotels, and destination info for each leg..."
        )
    else:
        # Single-destination trip message
        message_content = (
            f"Got it! Planning a trip:\n"
            f"📍 {trip_data.get('origin', '?')} → {trip_data.get('destination', '?')}\n"
            f"📅 {trip_data.get('departure_date', '?')}"
            f"{' to ' + trip_data['return_date'] if trip_data.get('return_date') else ' (one-way)'}\n"
            f"👥 {trip_data.get('num_travelers', 1)} traveler(s)\n"
            f"💰 Budget: {format_currency(trip_data.get('budget_limit'), trip_data.get('currency')) if trip_data.get('budget_limit') else 'flexible'}\n\n"
            "Searching for flights, hotels, and destination info..."
        )

    return {
        "trip_request": trip_data,
        "trip_legs": trip_legs,
        "token_usage": token_usage,
        "messages": [{"role": "assistant", "content": message_content}],
        "current_step": "intake_complete",
    }
