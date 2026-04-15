"""Deterministic parsing utilities for date and duration extraction from text."""

import re
from datetime import date, timedelta
from typing import Any


_MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_NUMBER_WORD_TO_INT = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def extract_explicit_departure_date(query: str) -> str:
    """Extract a single explicit natural-language departure date when present."""
    if not query.strip():
        return ""

    match = re.search(
        r"\b(?:on|from)?\s*(\d{1,2})(?:st|nd|rd|th)?\s+of\s+"
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        query,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""

    day = int(match.group(1))
    month = _MONTH_NAME_TO_NUMBER[match.group(2).lower()]
    today = date.today()

    try:
        parsed = date(today.year, month, day)
    except ValueError:
        return ""

    if parsed < today:
        try:
            parsed = date(today.year + 1, month, day)
        except ValueError:
            return ""

    return parsed.isoformat()


def extract_trip_duration_days(query: str) -> int:
    """Extract an explicit trip duration like 'for 2 days' or 'one-day trip'."""
    if not query.strip():
        return 0

    match = re.search(
        r"\b(?:for\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*[- ]?(day|days|night|nights)\b",
        query,
        flags=re.IGNORECASE,
    )
    if not match:
        day_trip_match = re.search(r"\b(day|night)\s+trip\b", query, flags=re.IGNORECASE)
        if day_trip_match:
            return 1
        return 0

    raw_value = match.group(1).lower()
    try:
        duration = int(raw_value)
    except ValueError:
        duration = _NUMBER_WORD_TO_INT.get(raw_value, 0)
    return max(0, duration)


def query_mentions_one_way(query: str) -> bool:
    """Return true when the user explicitly requests a one-way trip."""
    lowered = query.lower()
    return "one-way" in lowered or "one way" in lowered


def apply_free_text_trip_fallbacks(
    raw_trip_data: dict[str, Any],
    free_text_query: str,
    structured_fields: dict[str, Any],
) -> dict[str, Any]:
    """Use deterministic parsing to correct explicit dates and durations from free text."""
    if not free_text_query.strip():
        return raw_trip_data

    trip_data = dict(raw_trip_data)

    explicit_departure = extract_explicit_departure_date(free_text_query)
    if explicit_departure and not structured_fields.get("departure_date"):
        trip_data["departure_date"] = explicit_departure

    duration_days = extract_trip_duration_days(free_text_query)
    departure_date = trip_data.get("departure_date")
    is_one_way = query_mentions_one_way(free_text_query)
    if (
        duration_days > 0
        and departure_date
        and not structured_fields.get("return_date")
        and not structured_fields.get("check_out_date")
    ):
        end_date = date.fromisoformat(departure_date) + timedelta(days=duration_days)
        trip_data["check_out_date"] = end_date.isoformat()
        if is_one_way:
            trip_data["return_date"] = ""
        else:
            trip_data["return_date"] = end_date.isoformat()

    if is_one_way and not structured_fields.get("return_date"):
        trip_data["return_date"] = ""

    return trip_data
