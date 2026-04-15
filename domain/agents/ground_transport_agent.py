"""Ground Transport Agent — searches for trains, buses, and ferries."""

from infrastructure.apis.ground_transport_client import search_ground_transport as api_search_ground_transport
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def search_ground_transport(state: dict) -> dict:
    """LangGraph-style node: search ground transport for the trip request."""
    trip = state.get("trip_request", {})
    if not trip:
        logger.error("Ground transport search skipped because trip request is missing")
        return {"transport_options": [], "error": "No trip request found."}

    origin = trip.get("origin", "")
    destination = trip.get("destination", "")
    departure_date = trip.get("departure_date", "")

    if not all([origin, destination, departure_date]):
        logger.warning(
            "Ground transport search missing details origin=%s destination=%s date=%s",
            bool(origin), bool(destination), bool(departure_date),
        )
        return {
            "transport_options": [],
            "messages": [{"role": "assistant", "content": "Missing ground transport search details."}],
        }

    try:
        options = api_search_ground_transport(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            adults=trip.get("num_travelers", 1),
            currency=trip.get("currency", "EUR"),
        )
        return {
            "transport_options": options,
            "messages": [{"role": "assistant", "content": f"Found {len(options)} ground transport options."}],
        }
    except Exception as e:
        logger.exception("Ground transport search failed")
        return {
            "transport_options": [],
            "messages": [{"role": "assistant", "content": f"Ground transport search failed: {e}"}],
        }
