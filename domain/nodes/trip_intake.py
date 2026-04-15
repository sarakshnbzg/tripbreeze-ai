"""Trip Intake node — builds trip request from structured form fields
and/or a free-text query, using LLM tool calling to parse user input."""

from datetime import date, timedelta
from typing import Any

from langgraph.types import interrupt

from config import DEFAULT_STAY_NIGHTS
from domain.utils.dates import validate_future_date
from domain.nodes.trip_intake_schemas import (
    ExtractPreferences,
    ExtractTripDetails,
    ExtractMultiCityTrip,
    EvaluateDomain,
    PREFERENCES_PROMPT,
    FREE_TEXT_PROMPT,
    DOMAIN_GUARDRAIL_PROMPT,
)
from infrastructure.currency_utils import format_currency
from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

VALID_INTERESTS = {
    "food",
    "history",
    "nature",
    "art",
    "nightlife",
    "shopping",
    "outdoors",
    "family",
}

VALID_PACES = {"relaxed", "moderate", "packed"}


def _normalise_interests(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        key = str(item).strip().lower()
        if key in VALID_INTERESTS and key not in out:
            out.append(key)
    return out


def _normalise_pace(raw: object) -> str:
    key = str(raw or "").strip().lower()
    return key if key in VALID_PACES else ""


def _has_structured_trip_signal(data: dict[str, Any]) -> bool:
    """Return true when any meaningful travel-planning field is present."""
    signal_fields = (
        "origin",
        "destination",
        "departure_date",
        "return_date",
        "check_out_date",
        "preferences",
        "travel_class",
        "hotel_stars",
        "stops",
        "max_flight_price",
        "max_duration",
        "bags",
        "include_airlines",
        "exclude_airlines",
    )
    for field in signal_fields:
        value = data.get(field)
        if value not in (None, "", [], 0):
            return True
    return False


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


def _build_trip_legs(
    multi_city_data: dict[str, Any],
    origin: str,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert multi-city extraction to normalized trip legs.

    Each leg contains: origin, destination, departure_date, nights, needs_hotel, check_out_date.
    The origin for leg N+1 is the destination of leg N.
    """
    legs_raw = multi_city_data.get("legs", [])
    if not legs_raw:
        return []

    # Use origin from extraction, fallback to profile home_city, then passed origin
    trip_origin = multi_city_data.get("origin") or profile.get("home_city") or origin
    if not trip_origin:
        logger.warning("Multi-city trip has no origin")
        return []

    departure_date_str = multi_city_data.get("departure_date", "")
    if not departure_date_str:
        logger.warning("Multi-city trip has no departure date")
        return []

    try:
        current_date = date.fromisoformat(departure_date_str)
    except ValueError:
        logger.warning("Invalid departure date for multi-city: %s", departure_date_str)
        return []

    legs: list[dict[str, Any]] = []
    current_city = trip_origin

    for leg_data in legs_raw:
        destination = leg_data.get("destination", "")
        nights = leg_data.get("nights", 0)
        if not destination:
            continue

        check_out_date = None
        if nights > 0:
            check_out_date = (current_date + timedelta(days=nights)).isoformat()

        legs.append({
            "leg_index": len(legs),
            "origin": current_city,
            "destination": destination,
            "departure_date": current_date.isoformat(),
            "nights": nights,
            "needs_hotel": nights > 0,
            "check_out_date": check_out_date,
        })

        current_city = destination
        current_date = current_date + timedelta(days=nights)

    # Add return leg if returning to origin
    if multi_city_data.get("return_to_origin", True) and current_city != trip_origin:
        legs.append({
            "leg_index": len(legs),
            "origin": current_city,
            "destination": trip_origin,
            "departure_date": current_date.isoformat(),
            "nights": 0,
            "needs_hotel": False,
            "check_out_date": None,
        })

    logger.info("Built %d trip legs from multi-city extraction", len(legs))
    return legs


def _parse_clarification(
    llm,
    answer: str,
    missing_fields: list[str],
    question: str,
    model: str,
) -> tuple[dict[str, Any], dict | None]:
    """Parse a clarification answer, telling the LLM which fields it is filling.

    Without this hint, a bare answer like "Berlin" tends to be extracted as
    `destination` (and silently dropped if destination was already set),
    causing the clarification loop to ask the same question forever.
    """
    if not answer.strip():
        return {}, None

    logger.info(
        "Parsing clarification via LLM: fields=%s answer=%s",
        missing_fields,
        answer,
    )
    llm_with_tools = llm.bind_tools([ExtractTripDetails])
    prompt = (
        f"{FREE_TEXT_PROMPT.format(today=date.today().isoformat())}\n\n"
        "The user was previously asked this clarification question and their answer "
        "is below. Populate ONLY the fields listed in `target_fields` from the answer; "
        "leave every other field at its default. Do not reinterpret the answer as "
        "belonging to a different field.\n\n"
        f"<clarification_question>\n{question}\n</clarification_question>\n"
        f"<target_fields>\n{', '.join(missing_fields)}\n</target_fields>\n"
        f"<user_answer>\n{answer}\n</user_answer>"
    )
    response = invoke_with_retry(llm_with_tools, prompt)

    usage = extract_token_usage(response, model=model, node="trip_intake")

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Clarification extraction returned no tool calls")
        return {}, usage

    parsed = tool_calls[0].get("args", {}) or {}
    # Keep only the requested target fields — guard against the LLM filling others.
    filtered = {k: v for k, v in parsed.items() if k in missing_fields}
    return filtered, usage


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


def _normalise_hotel_stars(raw_hotel_stars: Any, profile: dict[str, Any]) -> list[int]:
    if raw_hotel_stars in (None, "", []):
        raw_hotel_stars = profile.get("preferred_hotel_stars", [])

    if isinstance(raw_hotel_stars, int):
        raw_values = [raw_hotel_stars]
    elif isinstance(raw_hotel_stars, list):
        raw_values = raw_hotel_stars
    else:
        raw_values = []

    normalised = []
    for value in raw_values:
        try:
            star = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= star <= 5 and star not in normalised:
            normalised.append(star)

    return sorted(normalised)


def _build_clarification_question(missing_fields: list[str], profile: dict[str, Any]) -> str:
    """Build a natural follow-up question asking for missing required fields."""
    parts: list[str] = []
    for field in missing_fields:
        if field == "destination":
            parts.append("where you'd like to go")
        elif field == "departure_date":
            parts.append("when you'd like to depart")
        elif field == "return_date":
            parts.append("when you'd like to return (or if this is a one-way trip)")
        elif field == "origin":
            parts.append("where you're flying from")
    if len(parts) == 1:
        question = f"Could you tell me {parts[0]}?"
    elif len(parts) == 2:
        question = f"Could you tell me {parts[0]} and {parts[1]}?"
    else:
        question = f"Could you tell me {', '.join(parts[:-1])}, and {parts[-1]}?"
    return f"I'd love to help plan your trip! {question}"


def _normalise_trip_data(raw_trip_data: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    hotel_stars_user_specified = raw_trip_data.get("hotel_stars") not in (None, "", [])

    departure_date = validate_future_date(raw_trip_data.get("departure_date") or "", "Departure date")
    return_date = validate_future_date(raw_trip_data.get("return_date") or "", "Return date")
    check_out_date = validate_future_date(raw_trip_data.get("check_out_date") or "", "Check-out date")

    if departure_date and return_date and return_date <= departure_date:
        raise ValueError(f"Return date ({return_date}) must be after departure date ({departure_date}).")
    if departure_date and check_out_date and check_out_date <= departure_date:
        raise ValueError(f"Check-out date ({check_out_date}) must be after departure date ({departure_date}).")

    if departure_date and not return_date and not check_out_date:
        check_out_date = (
            date.fromisoformat(departure_date) + timedelta(days=DEFAULT_STAY_NIGHTS)
        ).isoformat()
        logger.info(
            "One-way trip with no check-out date — defaulting to %s-night stay: check_out_date=%s",
            DEFAULT_STAY_NIGHTS,
            check_out_date,
        )

    trip_data = {
        "origin": raw_trip_data.get("origin") or "",
        "destination": raw_trip_data.get("destination") or "",
        "departure_date": departure_date,
        "return_date": return_date,
        "check_out_date": check_out_date,
        "num_travelers": raw_trip_data.get("num_travelers") or 1,
        "budget_limit": raw_trip_data.get("budget_limit") or 0,
        "currency": raw_trip_data.get("currency") or "EUR",
        "travel_class": raw_trip_data.get("travel_class") or "ECONOMY",
        "hotel_stars": _normalise_hotel_stars(raw_trip_data.get("hotel_stars"), profile),
        "hotel_stars_user_specified": hotel_stars_user_specified,
        "preferences": raw_trip_data.get("preferences") or "",
        "stops": raw_trip_data.get("stops"),
        "max_flight_price": raw_trip_data.get("max_flight_price") or 0,
        "max_duration": raw_trip_data.get("max_duration") or 0,
        "bags": raw_trip_data.get("bags") or 0,
        "emissions": bool(raw_trip_data.get("emissions")),
        "layover_duration_min": raw_trip_data.get("layover_duration_min") or 0,
        "layover_duration_max": raw_trip_data.get("layover_duration_max") or 0,
        "include_airlines": raw_trip_data.get("include_airlines") or [],
        "exclude_airlines": raw_trip_data.get("exclude_airlines") or [],
        "interests": _normalise_interests(raw_trip_data.get("interests")),
        "pace": _normalise_pace(raw_trip_data.get("pace")) or "moderate",
    }

    if not trip_data["origin"] and profile.get("home_city"):
        trip_data["origin"] = profile["home_city"]
    if not raw_trip_data.get("travel_class") and profile.get("travel_class"):
        trip_data["travel_class"] = profile["travel_class"]

    trip_data["num_travelers"] = max(1, int(trip_data["num_travelers"]))
    trip_data["budget_limit"] = float(trip_data["budget_limit"])
    trip_data["currency"] = str(trip_data["currency"]).upper()
    trip_data["travel_class"] = str(trip_data["travel_class"]).upper()

    # Normalise stops: must be 0, 1, or 2 (or None for no preference)
    raw_stops = trip_data.get("stops")
    if raw_stops is not None:
        try:
            stops_int = int(raw_stops)
            trip_data["stops"] = stops_int if 0 <= stops_int <= 2 else None
        except (TypeError, ValueError):
            trip_data["stops"] = None

    trip_data["max_flight_price"] = max(0, float(trip_data.get("max_flight_price") or 0))
    trip_data["max_duration"] = max(0, int(trip_data.get("max_duration") or 0))
    trip_data["bags"] = max(0, int(trip_data.get("bags") or 0))
    trip_data["layover_duration_min"] = max(0, int(trip_data.get("layover_duration_min") or 0))
    trip_data["layover_duration_max"] = max(0, int(trip_data.get("layover_duration_max") or 0))

    return trip_data


def trip_intake(state: dict) -> dict:
    """LangGraph node: build trip request from structured form fields and/or free text."""
    profile = state.get("user_profile", {})
    structured_fields = state.get("structured_fields", {})
    free_text_query = state.get("free_text_query", "")

    token_usage: list[dict] = []
    model = state.get("llm_model")
    provider = state.get("llm_provider")
    temperature = float(state.get("llm_temperature", 0))

    # Start with structured fields as the base
    raw_trip_data = dict(structured_fields)

    if free_text_query.strip() and not _has_structured_trip_signal(structured_fields):
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
            # Multi-city trip: build legs and derive trip_request from them
            trip_legs = _build_trip_legs(parsed_query, raw_trip_data.get("origin", ""), profile)
            if trip_legs:
                # Populate raw_trip_data from multi-city extraction for normalization
                raw_trip_data["origin"] = trip_legs[0]["origin"]
                raw_trip_data["destination"] = trip_legs[0]["destination"]  # First destination
                raw_trip_data["departure_date"] = trip_legs[0]["departure_date"]
                # Return date is the departure date of the last leg (return flight)
                raw_trip_data["return_date"] = trip_legs[-1]["departure_date"]
                # Copy shared fields from multi-city extraction
                for key in (
                    "num_travelers", "budget_limit", "currency", "preferences",
                    "stops", "hotel_stars", "travel_class", "interests", "pace",
                ):
                    if parsed_query.get(key) not in (None, "", []):
                        raw_trip_data[key] = parsed_query[key]
                logger.info("Multi-city trip with %d legs detected", len(trip_legs))
        else:
            # Single-destination: merge parsed values into raw_trip_data
            for key, value in parsed_query.items():
                not_empty = value is not None and value != "" and value != [] and (value != 0 or key == "stops")
                already_set = raw_trip_data.get(key) not in (None, "", []) if key != "stops" else raw_trip_data.get(key) is not None
                if not_empty and not already_set:
                    raw_trip_data[key] = value

            # If the free-text query had extra preferences, append to existing
            if parsed_query.get("preferences"):
                existing_prefs = raw_trip_data.get("preferences", "")
                ft_prefs = parsed_query["preferences"]
                if existing_prefs and ft_prefs not in existing_prefs:
                    raw_trip_data["preferences"] = f"{existing_prefs}, {ft_prefs}"
                elif not existing_prefs:
                    raw_trip_data["preferences"] = ft_prefs
    else:
        logger.info("Trip intake using structured fields only")

    # ── Check for missing required fields and ask the user ──
    # Only ask for clarification when the user provided free text without structured
    # form fields (the UI already validates structured submissions). Uses a loop so
    # that if the user's answer still leaves gaps, we ask again. LangGraph replays
    # answered interrupts on re-run, so each iteration's interrupt() returns the
    # previously supplied answer automatically.
    if free_text_query.strip() and not _has_structured_trip_signal(structured_fields):
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
            clarification_answer = interrupt({
                "type": "clarification",
                "question": question,
                "missing_fields": missing_fields,
            })
            # On resume: parse the user's answer and merge into raw_trip_data
            if not clarification_answer:
                break  # empty answer — proceed with what we have
            logger.info("Clarification answer received: %s", clarification_answer)
            llm = create_chat_model(provider, model, temperature=temperature)
            parsed_answer, usage = _parse_clarification(
                llm,
                clarification_answer,
                missing_fields,
                question,
                model=model,
            )
            if usage:
                token_usage.append(usage)
            for key, value in parsed_answer.items():
                not_empty = value is not None and value != "" and value != [] and (value != 0 or key == "stops")
                already_set = raw_trip_data.get(key) not in (None, "", []) if key != "stops" else raw_trip_data.get(key) is not None
                if not_empty and not already_set:
                    raw_trip_data[key] = value

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
