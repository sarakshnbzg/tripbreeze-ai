"""Prompt/context and response helpers for the trip finaliser."""

import json

from application.workflow_types import WorkflowStep
from domain.utils.sanitize import sanitise_untrusted_text
from domain.nodes.trip_finaliser_support import (
    _build_multi_city_daily_plans,
    _multi_city_flight_summary,
)
from domain.utils.dates import trip_duration_with_dates


PACE_TO_ACTIVITIES = {"relaxed": 2, "moderate": 3, "packed": 4}


def _finaliser_success_response(
    *,
    itinerary,
    render_markdown,
    rag_sources: list[str],
    rag_trace: list[dict],
    token_usage: list[dict],
    finaliser_metadata: dict | None = None,
    selected_hotel: dict | None = None,
    selected_hotels: list[dict] | None = None,
    state: dict | None = None,
    stream_markdown=None,
) -> dict:
    markdown = render_markdown(itinerary)
    if state is not None and stream_markdown is not None:
        markdown = stream_markdown(state, itinerary, markdown)
    response = {
        "final_itinerary": markdown,
        "itinerary_data": itinerary.model_dump(),
        "rag_sources": rag_sources,
        "rag_trace": rag_trace,
        "token_usage": token_usage,
        "finaliser_metadata": finaliser_metadata or {},
        "messages": [{"role": "assistant", "content": markdown}],
        "current_step": WorkflowStep.FINALISED,
    }
    if selected_hotel is not None:
        response["selected_hotel"] = selected_hotel
    if selected_hotels is not None:
        response["selected_hotels"] = selected_hotels
    return response


def _finaliser_error_response_with_tokens(
    *,
    display_message: str,
    token_usage: list[dict],
    assistant_message: str | None = None,
    finaliser_metadata: dict | None = None,
) -> dict:
    return {
        "final_itinerary": display_message,
        "itinerary_data": {},
        "token_usage": token_usage,
        "finaliser_metadata": finaliser_metadata or {},
        "messages": [{"role": "assistant", "content": assistant_message or display_message}],
        "current_step": WorkflowStep.FINALISED,
    }


def _format_attraction_candidates(candidates: list[dict]) -> str:
    if not candidates:
        return "None"
    lines = []
    for idx, item in enumerate(candidates, start=1):
        rating = item.get("rating")
        rating_str = f" ★{rating}" if rating else ""
        addr = item.get("address") or ""
        category = item.get("category") or "general"
        destination = item.get("destination") or ""
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        coord_str = ""
        if latitude is not None and longitude is not None:
            coord_str = f" ({latitude:.5f}, {longitude:.5f})"
        maps_url = item.get("maps_url") or ""
        lines.append(
            f"{idx}. {item.get('name', '?')} [{category}]{rating_str}"
            + (f" — {addr}" if addr else "")
            + (f" [{destination}]" if destination else "")
            + coord_str
            + (f" <{maps_url}>" if maps_url else "")
        )
    return "\n".join(lines)


def _single_city_plan_context(trip_request: dict, candidates: list[dict]) -> dict:
    """Build the prompt variables needed for day-by-day planning."""
    num_days, day_dates = trip_duration_with_dates(trip_request)
    departure_day_guidance = ""
    return_date = str(trip_request.get("return_date", "") or "").strip()
    departure_date = str(trip_request.get("departure_date", "") or "").strip()
    if return_date and return_date != departure_date:
        day_dates = day_dates + [return_date]
        num_days = len(day_dates)
        departure_day_guidance = (
            f"Important: Day {num_days} is the departure day on {return_date}. "
            "Treat it as a lighter plan, not a full sightseeing day."
        )
    pace = str(trip_request.get("pace") or "moderate").lower()
    activities_per_day = PACE_TO_ACTIVITIES.get(pace, 3)
    interests = trip_request.get("interests") or []
    return {
        "num_days": num_days,
        "day_dates": ", ".join(
            f"Day {i + 1}={d}" for i, d in enumerate(day_dates)
        ) or "unknown",
        "pace": pace,
        "activities_per_day": activities_per_day,
        "interests": ", ".join(interests) if interests else "no explicit preference",
        "attraction_candidates": _format_attraction_candidates(candidates),
        "departure_day_guidance": departure_day_guidance,
    }


def _multi_city_plan_context(trip_request: dict, trip_legs: list[dict], candidates: list[dict]) -> dict:
    seeded_plans = _build_multi_city_daily_plans(trip_legs)
    pace = str(trip_request.get("pace") or "moderate").lower()
    activities_per_day = PACE_TO_ACTIVITIES.get(pace, 3)
    interests = trip_request.get("interests") or []
    departure_day_guidance = ""
    if seeded_plans:
        last_day = seeded_plans[-1]
        if "Departure day" in (last_day.theme or ""):
            departure_day_guidance = (
                f"Important: Day {last_day.day_number} is the departure day on {last_day.date}. "
                "Treat it as a lighter travel day, not a full sightseeing day."
            )
    return {
        "num_days": len(seeded_plans),
        "day_dates": ", ".join(f"Day {day.day_number}={day.date}" for day in seeded_plans) or "unknown",
        "pace": pace,
        "activities_per_day": activities_per_day,
        "interests": ", ".join(interests) if interests else "no explicit preference",
        "attraction_candidates": _format_attraction_candidates(candidates),
        "departure_day_guidance": departure_day_guidance,
    }


def _traveler_preference_context(trip_request: dict, user_profile: dict) -> str:
    preferred_airlines = ", ".join(user_profile.get("preferred_airlines", []) or []) or "none saved"
    preferred_hotel_stars = ", ".join(str(star) for star in user_profile.get("preferred_hotel_stars", []) or []) or "none saved"
    outbound_window = user_profile.get("preferred_outbound_time_window") or [0, 23]
    return_window = user_profile.get("preferred_return_time_window") or [0, 23]
    requested_hotel_stars = ", ".join(str(star) for star in trip_request.get("hotel_stars", []) or []) or "not specified"
    interests = ", ".join(trip_request.get("interests", []) or []) or "not specified"
    pace = trip_request.get("pace") or "moderate"
    preferences = sanitise_untrusted_text(trip_request.get("preferences") or "", context="traveler_preferences") or "none"
    return (
        f"Travel class: {trip_request.get('travel_class') or user_profile.get('travel_class') or 'not specified'}\n"
        f"Preferred airlines: {preferred_airlines}\n"
        f"Preferred hotel stars from profile: {preferred_hotel_stars}\n"
        f"Requested hotel stars for this trip: {requested_hotel_stars}\n"
        f"Preferred outbound time window: {outbound_window}\n"
        f"Preferred return time window: {return_window}\n"
        f"Interests: {interests}\n"
        f"Pace: {pace}\n"
        f"Free-text preferences: {preferences}"
    )


def _selected_flight_context(selected_flight: dict, trip_request: dict) -> str:
    """Build a stable finaliser prompt block that clearly shows outbound and return legs."""
    if not selected_flight:
        return "No flight selected"

    flight_payload = json.dumps(selected_flight, indent=2)
    outbound_summary = selected_flight.get("outbound_summary", "")
    return_summary = selected_flight.get("return_summary", "")
    is_round_trip = bool(trip_request.get("return_date"))

    sections = ["Structured flight data:", flight_payload]
    if outbound_summary:
        sections.append(f"Outbound flight summary: {outbound_summary}")
    if is_round_trip:
        if return_summary:
            sections.append(f"Return flight summary: {return_summary}")
        else:
            sections.append("Return flight summary: Not available.")

    return "\n\n".join(sections)


def _selected_hotel_context(selected_hotel: dict) -> str:
    if not selected_hotel:
        return "No hotel selected"
    payload = json.dumps(selected_hotel, indent=2)
    reasons = selected_hotel.get("preference_reasons") or []
    if not reasons:
        return payload
    return payload + "\n\nPreference matches: " + ", ".join(reasons)


def _selected_flights_context(selected_flights: list[dict], currency: str) -> str:
    if not selected_flights:
        return "No flights selected"

    rendered = []
    for idx, flight in enumerate(selected_flights, start=1):
        summary = _multi_city_flight_summary(flight, currency) if flight else "Flight details unavailable"
        payload = json.dumps(flight, indent=2) if flight else "{}"
        rendered.append(f"Leg {idx} flight summary: {summary}\nStructured flight data:\n{payload}")
    return "\n\n".join(rendered)


def _selected_hotels_context(selected_hotels: list[dict]) -> str:
    if not selected_hotels:
        return "No hotels selected"

    rendered = []
    for idx, hotel in enumerate(selected_hotels, start=1):
        if not hotel:
            rendered.append(f"Leg {idx} hotel: No hotel selected")
            continue
        rendered.append(f"Leg {idx} hotel:\n{_selected_hotel_context(hotel)}")
    return "\n\n".join(rendered)


def _build_finaliser_metadata(
    *,
    state: dict,
    mode: str,
    diagnostics: dict,
    used_fallback: bool,
    fallback_reason: str = "",
) -> dict:
    return {
        "mode": mode,
        "provider": state.get("llm_provider", ""),
        "model": state.get("llm_model", ""),
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "react_loop": diagnostics,
    }
