"""Trip Intake node — builds trip request from structured form fields
and uses LLM tool calling only to parse the free-text preferences."""

from typing import Any

from pydantic import BaseModel, Field

from infrastructure.currency_utils import format_currency
from infrastructure.llms.model_factory import create_chat_model
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

PREFERENCES_PROMPT = """You are a travel planning assistant.
The user provided free-text special requests for their trip.
Extract any structured filter criteria from the text.
Always call the provided ExtractPreferences tool exactly once.
If no relevant criteria are mentioned, use the default values.
"""


class ExtractPreferences(BaseModel):
    """Structured filters extracted from free-text special requests."""

    stops: int | None = Field(
        default=None,
        description=(
            "Maximum number of stops for flights. "
            "Use 0 for nonstop/direct flights only, 1 for 1 stop or fewer, "
            "2 for 2 stops or fewer. Leave None if not specified."
        ),
    )
    max_flight_price: float = Field(
        default=0,
        description="Maximum price per person for flights. Use 0 if not specified.",
    )
    max_duration: int = Field(
        default=0,
        description="Maximum total flight duration in minutes. E.g. 'under 5 hours' = 300. Use 0 if not specified.",
    )
    bags: int = Field(
        default=0,
        description="Number of carry-on bags. Use 0 if not specified.",
    )
    emissions: bool = Field(
        default=False,
        description="Set to true if the user wants eco-friendly / low-emission flights only.",
    )
    layover_duration_min: int = Field(
        default=0,
        description="Minimum layover duration in minutes. Use 0 if not specified.",
    )
    layover_duration_max: int = Field(
        default=0,
        description="Maximum layover duration in minutes. Use 0 if not specified.",
    )
    include_airlines: list[str] = Field(
        default_factory=list,
        description=(
            "Airlines to include (only show these). Use 2-letter IATA codes (e.g. 'LH' for Lufthansa) "
            "or alliance names: STAR_ALLIANCE, SKYTEAM, ONEWORLD. Empty list if not specified."
        ),
    )
    exclude_airlines: list[str] = Field(
        default_factory=list,
        description=(
            "Airlines to exclude (hide these). Use 2-letter IATA codes (e.g. 'FR' for Ryanair) "
            "or alliance names: STAR_ALLIANCE, SKYTEAM, ONEWORLD. Empty list if not specified."
        ),
    )
    hotel_stars: list[int] = Field(
        default_factory=list,
        description="Preferred hotel star ratings from 1 to 5. Use an empty list if not specified.",
    )
    travel_class: str = Field(
        default="",
        description="Cabin class if mentioned: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST. Empty if not specified.",
    )


def _parse_preferences(llm, preferences: str) -> dict[str, Any]:
    """Use LLM tool calling to extract structured filters from free-text preferences."""
    if not preferences.strip():
        return {}

    logger.info("Parsing preferences via LLM: %s", preferences)
    llm_with_tools = llm.bind_tools([ExtractPreferences])
    response = llm_with_tools.invoke(
        f"{PREFERENCES_PROMPT}\n\nSpecial requests: {preferences}"
    )

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        logger.warning("Preferences extraction returned no tool calls")
        return {}

    return tool_calls[0].get("args", {})


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


def _normalise_trip_data(raw_trip_data: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    hotel_stars_user_specified = raw_trip_data.get("hotel_stars") not in (None, "", [])
    trip_data = {
        "origin": raw_trip_data.get("origin") or "",
        "destination": raw_trip_data.get("destination") or "",
        "departure_date": raw_trip_data.get("departure_date") or "",
        "return_date": raw_trip_data.get("return_date") or "",
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
    """LangGraph node: build trip request from structured form fields."""
    profile = state.get("user_profile", {})
    structured_fields = state.get("structured_fields", {})

    logger.info("Trip intake using structured fields")
    raw_trip_data = dict(structured_fields)

    preferences = raw_trip_data.get("preferences", "")
    if preferences.strip():
        llm = create_chat_model(
            state.get("llm_provider"),
            state.get("llm_model"),
            temperature=0,
        )
        parsed = _parse_preferences(llm, preferences)
        # Merge LLM-extracted filters into trip data
        for key in (
            "stops", "max_flight_price", "max_duration", "bags", "emissions",
            "layover_duration_min", "layover_duration_max",
            "include_airlines", "exclude_airlines",
            "hotel_stars", "travel_class",
        ):
            value = parsed.get(key)
            if value is not None and value != "" and value != []:
                raw_trip_data[key] = value

    try:
        trip_data = _normalise_trip_data(raw_trip_data, profile)
    except Exception as exc:
        logger.exception("Trip intake failed during normalisation")
        return {
            "error": f"Could not normalise trip details: {exc}",
            "current_step": "intake_error",
        }

    logger.info(
        "Trip intake complete origin=%s destination=%s departure=%s return=%s travelers=%s",
        trip_data.get("origin"),
        trip_data.get("destination"),
        trip_data.get("departure_date"),
        trip_data.get("return_date"),
        trip_data.get("num_travelers"),
    )

    return {
        "trip_request": trip_data,
        "messages": [
            {
                "role": "assistant",
                "content": (
                    f"Got it! Planning a trip:\n"
                    f"📍 {trip_data.get('origin', '?')} → {trip_data.get('destination', '?')}\n"
                    f"📅 {trip_data.get('departure_date', '?')} to {trip_data.get('return_date', '?')}\n"
                    f"👥 {trip_data.get('num_travelers', 1)} traveler(s)\n"
                    f"💰 Budget: {format_currency(trip_data.get('budget_limit'), trip_data.get('currency')) if trip_data.get('budget_limit') else 'flexible'}\n\n"
                    "Searching for flights, hotels, and destination info..."
                ),
            }
        ],
        "current_step": "intake_complete",
    }
