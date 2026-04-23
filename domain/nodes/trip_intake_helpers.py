"""Deterministic helper functions for the trip intake node."""

import re
from datetime import date, timedelta
from typing import Any

from settings import DEFAULT_STAY_NIGHTS
from domain.utils.dates import validate_future_date
from infrastructure.currency_utils import format_currency
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
_DURATION_PATTERN = re.compile(
    r"\bfor\s+(?:(?P<article>a|an|one)\s+)?(?P<count>\d+)?\s*(?P<unit>day|days|night|nights|week|weeks)\b",
    re.IGNORECASE,
)
_CITY_STAY_PATTERN = re.compile(
    r"\b(?P<city>[A-Z][A-Za-z' -]*(?:\s+[A-Z][A-Za-z' -]*)*)\s+(?P<nights>\d+)\s*(?P<unit>day|days|night|nights)\b"
)


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


def _infer_stay_length_days(query: str) -> int | None:
    """Infer stay length from simple duration phrases in free text."""
    if not query.strip():
        return None

    match = _DURATION_PATTERN.search(query)
    if not match:
        return None

    unit = match.group("unit").lower()
    article = (match.group("article") or "").lower()
    count_text = match.group("count")

    if count_text:
        count = int(count_text)
    elif article in {"a", "an", "one"}:
        count = 1
    else:
        return None

    if count <= 0:
        return None
    if unit in {"week", "weeks"}:
        return count * 7
    return count


def _merge_has_value(key: str, value: Any) -> bool:
    if key == "stops":
        return value is not None
    if key == "is_one_way":
        return value is True
    return value not in (None, "", [])


def _infer_multi_city_data(query: str) -> dict[str, Any]:
    """Deterministically recover simple multi-city legs from free text."""
    legs: list[dict[str, Any]] = []
    for match in _CITY_STAY_PATTERN.finditer(query):
        city = " ".join(str(match.group("city") or "").split()).strip(" ,.-")
        city = re.sub(
            r"^(?:plan\s+trip\s+to|trip\s+to|plan\s+to\s+visit|visit|go\s+to|fly\s+to|stay\s+in|then|and)\s+",
            "",
            city,
            flags=re.IGNORECASE,
        ).strip(" ,.-")
        if not city:
            continue

        try:
            nights = int(match.group("nights"))
        except (TypeError, ValueError):
            continue
        if nights <= 0:
            continue

        if legs and city.lower() == str(legs[-1]["destination"]).lower():
            continue
        legs.append({"destination": city, "nights": nights})

    if len(legs) < 2:
        return {}

    lowered = query.lower()
    inferred: dict[str, Any] = {
        "legs": legs,
        "return_to_origin": not bool(re.search(r"\bone[\s-]?way\b|\bopen jaw\b|\bopen-jaw\b|\bno return\b", lowered)),
    }

    if re.search(r"\bwith my (husband|wife|partner)\b", lowered):
        inferred["num_travelers"] = 2

    budget_match = re.search(
        r"\b(?:with\s+(?:a\s+)?)?(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>eur|euro|euros|usd|dollars|gbp|pounds)\b",
        lowered,
    )
    if budget_match:
        amount_text = str(budget_match.group("amount") or "").replace(",", "")
        try:
            inferred["budget_limit"] = float(amount_text)
        except ValueError:
            pass
        currency = str(budget_match.group("currency") or "").lower()
        inferred["currency"] = {
            "eur": "EUR",
            "euro": "EUR",
            "euros": "EUR",
            "usd": "USD",
            "dollars": "USD",
            "gbp": "GBP",
            "pounds": "GBP",
        }.get(currency, "")

    return inferred


def _has_structured_trip_signal(structured_fields: dict[str, Any]) -> bool:
    """Return True when form inputs clearly indicate a trip-planning request."""
    if not structured_fields:
        return False

    trip_fields = (
        "origin",
        "destination",
        "departure_date",
        "return_date",
        "check_out_date",
        "is_one_way",
        "multi_city_legs",
    )
    return any(structured_fields.get(field) not in (None, "", []) for field in trip_fields)


def _build_trip_legs(
    multi_city_data: dict[str, Any],
    origin: str,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert multi-city extraction to normalized trip legs."""
    legs_raw = multi_city_data.get("legs", [])
    if not legs_raw:
        return []

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


def _build_trip_legs_from_form(
    structured_fields: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build multi-city legs directly from the structured form payload."""
    form_legs = structured_fields.get("multi_city_legs") or []
    origin = structured_fields.get("origin") or profile.get("home_city") or ""
    departure_date_str = structured_fields.get("departure_date", "")
    return_to_origin = structured_fields.get("return_to_origin", True)

    if not (origin and departure_date_str and form_legs):
        return [], {}

    trip_legs: list[dict[str, Any]] = []
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

    if not trip_legs:
        return [], {}

    return trip_legs, {
        "origin": trip_legs[0]["origin"],
        "destination": trip_legs[0]["destination"],
        "departure_date": trip_legs[0]["departure_date"],
        "return_date": trip_legs[-1]["departure_date"],
    }


def _merge_single_city_parsed_query(
    raw_trip_data: dict[str, Any],
    parsed_query: dict[str, Any],
    *,
    revision_mode: bool,
) -> None:
    """Merge single-city free-text extraction into the working trip payload."""
    for key, value in parsed_query.items():
        not_empty = value is not None and value != "" and value != [] and (value != 0 or key == "stops")
        already_set = raw_trip_data.get(key) not in (None, "", []) if key != "stops" else raw_trip_data.get(key) is not None
        if not_empty and (revision_mode or not already_set):
            raw_trip_data[key] = value

    if parsed_query.get("preferences"):
        existing_prefs = raw_trip_data.get("preferences", "")
        ft_prefs = parsed_query["preferences"]
        if existing_prefs and ft_prefs not in existing_prefs:
            raw_trip_data["preferences"] = f"{existing_prefs}, {ft_prefs}"
        elif not existing_prefs:
            raw_trip_data["preferences"] = ft_prefs


def _recover_multi_city_trip(
    raw_trip_data: dict[str, Any],
    free_text_query: str,
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Recover simple multi-city structure from a single-city free-text parse."""
    inferred_multi_city_data = _infer_multi_city_data(free_text_query)
    if not inferred_multi_city_data:
        return [], None

    logger.info(
        "Recovered multi-city structure from free text fallback with %d legs",
        len(inferred_multi_city_data.get("legs", [])),
    )
    if not raw_trip_data.get("destination") and inferred_multi_city_data.get("legs"):
        raw_trip_data["destination"] = inferred_multi_city_data["legs"][0]["destination"]
    for key in ("num_travelers", "budget_limit", "currency"):
        if not _merge_has_value(key, raw_trip_data.get(key)) and _merge_has_value(key, inferred_multi_city_data.get(key)):
            raw_trip_data[key] = inferred_multi_city_data[key]

    if not raw_trip_data.get("departure_date"):
        return [], inferred_multi_city_data

    multi_city_seed = {
        **inferred_multi_city_data,
        "origin": raw_trip_data.get("origin") or "",
        "departure_date": raw_trip_data.get("departure_date") or "",
        "return_to_origin": False if raw_trip_data.get("is_one_way") else inferred_multi_city_data.get("return_to_origin", True),
    }
    built_legs = _build_trip_legs(multi_city_seed, raw_trip_data.get("origin", ""), profile)
    if not built_legs:
        return [], inferred_multi_city_data

    raw_trip_data["origin"] = built_legs[0]["origin"]
    raw_trip_data["destination"] = built_legs[0]["destination"]
    raw_trip_data["departure_date"] = built_legs[0]["departure_date"]
    raw_trip_data["return_date"] = built_legs[-1]["departure_date"]
    return built_legs, inferred_multi_city_data


def _apply_clarification_duration_fallback(
    parsed_answer: dict[str, Any],
    answer: str,
    raw_trip_data: dict[str, Any],
    missing_fields: list[str],
) -> dict[str, Any]:
    """Convert clarification duration phrases into concrete trip dates."""
    inferred_days = _infer_stay_length_days(answer)
    if not inferred_days:
        return parsed_answer

    departure_date = str(parsed_answer.get("departure_date") or raw_trip_data.get("departure_date") or "").strip()
    if not departure_date:
        return parsed_answer

    try:
        inferred_end = (date.fromisoformat(departure_date) + timedelta(days=inferred_days)).isoformat()
    except ValueError:
        return parsed_answer

    next_answer = dict(parsed_answer)
    if "return_date" in missing_fields and not raw_trip_data.get("is_one_way"):
        next_answer["return_date"] = inferred_end
    if "check_out_date" in missing_fields or (
        "return_date" in missing_fields and not raw_trip_data.get("is_one_way")
    ):
        next_answer["check_out_date"] = inferred_end
    return next_answer


def _apply_clarification_intent_fallback(
    parsed_answer: dict[str, Any],
    answer: str,
    missing_fields: list[str],
) -> dict[str, Any]:
    """Recover obvious yes/no trip intent from short clarification answers."""
    lowered = answer.strip().lower()
    if "return_date" not in missing_fields:
        return parsed_answer

    if re.search(r"\bone[\s-]?way\b|\bno return\b|\bnot coming back\b", lowered):
        next_answer = dict(parsed_answer)
        next_answer["is_one_way"] = True
        next_answer["return_date"] = ""
        return next_answer

    return parsed_answer


def _repair_invalid_duration_dates(
    raw_trip_data: dict[str, Any],
    free_text_query: str,
    parsed_answer: dict[str, Any],
    missing_fields: list[str],
) -> None:
    """Recompute stale end dates after a clarification updates departure_date."""
    if "departure_date" not in missing_fields:
        return
    if not parsed_answer.get("departure_date"):
        return

    inferred_days = _infer_stay_length_days(free_text_query)
    if not inferred_days:
        return

    departure_date = str(raw_trip_data.get("departure_date") or "").strip()
    if not departure_date:
        return

    try:
        departure = date.fromisoformat(departure_date)
    except ValueError:
        return

    repaired_end = (departure + timedelta(days=inferred_days)).isoformat()
    current_return = str(raw_trip_data.get("return_date") or "").strip()
    current_check_out = str(raw_trip_data.get("check_out_date") or "").strip()

    if current_return:
        try:
            if date.fromisoformat(current_return) <= departure:
                raw_trip_data["return_date"] = repaired_end
        except ValueError:
            raw_trip_data["return_date"] = repaired_end

    if current_check_out:
        try:
            if date.fromisoformat(current_check_out) <= departure:
                raw_trip_data["check_out_date"] = repaired_end
        except ValueError:
            raw_trip_data["check_out_date"] = repaired_end


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


def _missing_required_fields(raw_trip_data: dict[str, Any]) -> list[str]:
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
    return missing_fields


def _merge_clarification_answer(
    raw_trip_data: dict[str, Any],
    parsed_answer: dict[str, Any],
    inferred_multi_city_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge clarification results and return updated inferred multi-city seed."""
    next_inferred = inferred_multi_city_data
    if parsed_answer.get("legs") or "return_to_origin" in parsed_answer:
        next_inferred = dict(inferred_multi_city_data or {})
        if parsed_answer.get("legs"):
            next_inferred["legs"] = parsed_answer["legs"]
            if not raw_trip_data.get("destination"):
                raw_trip_data["destination"] = parsed_answer["legs"][0].get("destination", "")
        if "return_to_origin" in parsed_answer:
            next_inferred["return_to_origin"] = parsed_answer["return_to_origin"]
            if parsed_answer["return_to_origin"] is False:
                raw_trip_data["is_one_way"] = True
                raw_trip_data["return_date"] = ""

    for key, value in parsed_answer.items():
        not_empty = _merge_has_value(key, value) or (key == "return_date" and value == "")
        already_set = _merge_has_value(key, raw_trip_data.get(key))
        if not_empty and not already_set:
            raw_trip_data[key] = value

    return next_inferred


def _infer_missing_dates_from_query(raw_trip_data: dict[str, Any], free_text_query: str) -> None:
    """Use simple duration phrases to derive missing end dates."""
    if (
        not free_text_query.strip()
        or not raw_trip_data.get("departure_date")
        or raw_trip_data.get("return_date")
        or raw_trip_data.get("check_out_date")
    ):
        return

    inferred_days = _infer_stay_length_days(free_text_query)
    if not inferred_days:
        return

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


def _fill_origin_from_profile_if_only_gap(raw_trip_data: dict[str, Any], profile: dict[str, Any]) -> None:
    """Use the saved home city only when origin is the last required trip gap."""
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


def _finalise_inferred_multi_city_trip(
    raw_trip_data: dict[str, Any],
    inferred_multi_city_data: dict[str, Any] | None,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build trip legs after clarification once departure data is finally available."""
    if not inferred_multi_city_data or not raw_trip_data.get("departure_date"):
        return []

    multi_city_seed = {
        **inferred_multi_city_data,
        "origin": raw_trip_data.get("origin") or "",
        "departure_date": raw_trip_data.get("departure_date") or "",
        "return_to_origin": False if raw_trip_data.get("is_one_way") else inferred_multi_city_data.get("return_to_origin", True),
    }
    trip_legs = _build_trip_legs(multi_city_seed, raw_trip_data.get("origin", ""), profile)
    if trip_legs:
        raw_trip_data["origin"] = trip_legs[0]["origin"]
        raw_trip_data["destination"] = trip_legs[0]["destination"]
        raw_trip_data["departure_date"] = trip_legs[0]["departure_date"]
        raw_trip_data["return_date"] = trip_legs[-1]["departure_date"]
    return trip_legs


def _build_trip_intake_message(trip_data: dict[str, Any], trip_legs: list[dict[str, Any]]) -> str:
    """Build the assistant confirmation message after intake succeeds."""
    if trip_legs:
        legs_summary = " → ".join(leg["destination"] for leg in trip_legs)
        return (
            f"Got it! Planning a multi-city trip:\n"
            f"📍 {trip_data.get('origin', '?')} → {legs_summary}\n"
            f"📅 {trip_data.get('departure_date', '?')} to {trip_data.get('return_date', '?')}\n"
            f"👥 {trip_data.get('num_travelers', 1)} traveler(s)\n"
            f"💰 Budget: {format_currency(trip_data.get('budget_limit'), trip_data.get('currency')) if trip_data.get('budget_limit') else 'flexible'}\n\n"
            "Searching for flights, hotels, and destination info for each leg..."
        )

    return (
        f"Got it! Planning a trip:\n"
        f"📍 {trip_data.get('origin', '?')} → {trip_data.get('destination', '?')}\n"
        f"📅 {trip_data.get('departure_date', '?')}"
        f"{' to ' + trip_data['return_date'] if trip_data.get('return_date') else ' (one-way)'}\n"
        f"👥 {trip_data.get('num_travelers', 1)} traveler(s)\n"
        f"💰 Budget: {format_currency(trip_data.get('budget_limit'), trip_data.get('currency')) if trip_data.get('budget_limit') else 'flexible'}\n\n"
        "Searching for flights, hotels, and destination info..."
    )


def _apply_profile_defaults(raw_trip_data: dict[str, Any], profile: dict[str, Any]) -> None:
    """Fill missing trip fields from the saved user profile before clarification."""
    if not raw_trip_data.get("origin") and profile.get("home_city"):
        raw_trip_data["origin"] = profile["home_city"]
    if not raw_trip_data.get("travel_class") and profile.get("travel_class"):
        raw_trip_data["travel_class"] = profile["travel_class"]


def _normalise_trip_data(raw_trip_data: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    hotel_stars_user_specified = raw_trip_data.get("hotel_stars") not in (None, "", [])

    departure_date = validate_future_date(raw_trip_data.get("departure_date") or "", "Departure date")
    return_date = validate_future_date(raw_trip_data.get("return_date") or "", "Return date")
    check_out_date = validate_future_date(raw_trip_data.get("check_out_date") or "", "Check-out date")

    if departure_date and return_date and return_date <= departure_date:
        raise ValueError(f"Return date ({return_date}) must be after departure date ({departure_date}).")
    if departure_date and check_out_date and check_out_date <= departure_date:
        raise ValueError(f"Check-out date ({check_out_date}) must be after departure date ({departure_date}).")

    is_one_way = bool(raw_trip_data.get("is_one_way"))
    if departure_date and check_out_date and not return_date and not is_one_way:
        return_date = check_out_date

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
