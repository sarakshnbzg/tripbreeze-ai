"""Memory Updater node — persists learned preferences to long-term memory."""

from infrastructure.persistence.memory_store import update_profile_from_trip
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _build_history_destination_label(trip: dict) -> str:
    """Create a compact history label, including origin when available."""
    trip_legs = trip.get("trip_legs") or []
    origin = str(trip.get("origin", "")).strip()
    if not trip_legs:
        destination = str(trip.get("destination", "")).strip()
        if destination and origin:
            return f"{destination} from {origin}"
        return destination

    route: list[str] = []
    for leg in trip_legs:
        destination = str(leg.get("destination", "")).strip()
        if not destination:
            continue
        if route and route[-1] == destination:
            continue
        route.append(destination)

    if origin and len(route) > 1 and route[-1] == origin:
        route.pop()

    if not route:
        return trip.get("destination", "")
    if len(route) == 1:
        return route[0]
    route_label = " -> ".join(route)
    if origin:
        return f"{route_label} from {origin}"
    return route_label


def memory_updater(state: dict) -> dict:
    """LangGraph node: update user profile with info from this session."""
    user_id = state.get("user_id", "default_user")
    trip = state.get("trip_request", {})

    if not trip:
        logger.info("Memory updater skipped because trip data is missing for user_id=%s", user_id)
        return {"current_step": "done"}

    trip_data = {
        "destination": _build_history_destination_label({
            **trip,
            "trip_legs": state.get("trip_legs", []),
        }),
        "departure_date": trip.get("departure_date", ""),
        "return_date": trip.get("return_date", ""),
        "home_city": trip.get("origin", ""),
        "travel_class": trip.get("travel_class", ""),
        "passport_country": state.get("user_profile", {}).get("passport_country", ""),
        "final_itinerary": state.get("final_itinerary", ""),
        "pdf_state": {
            "selected_flight": state.get("selected_flight", {}),
            "selected_hotel": state.get("selected_hotel", {}),
            "budget": state.get("budget", {}),
        },
    }

    updated_profile = update_profile_from_trip(user_id, trip_data)
    logger.info(
        "Memory updated for user_id=%s destination=%s past_trips=%s",
        user_id,
        trip_data.get("destination"),
        len(updated_profile.get("past_trips", [])),
    )

    return {
        "user_profile": updated_profile,
        "current_step": "done",
        "messages": [{"role": "system", "content": "User preferences updated in long-term memory."}],
    }
