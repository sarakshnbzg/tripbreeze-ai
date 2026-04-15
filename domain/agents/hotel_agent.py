"""Hotel Agent — searches for hotels and formats results for the graph state."""

from config import HOTEL_STARS
from infrastructure.apis.serpapi_client import search_hotels as api_search_hotels
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def search_hotels(state: dict) -> dict:
    """LangGraph node: search for hotels based on trip request."""
    trip = state.get("trip_request", {})
    if not trip:
        logger.error("Hotel search skipped because trip request is missing")
        return {"hotel_options": [], "error": "No trip request found."}

    destination = trip.get("destination", "")
    check_in = trip.get("departure_date", "")
    check_out = trip.get("return_date", "") or trip.get("check_out_date", "")

    if not all([destination, check_in, check_out]):
        logger.warning(
            "Hotel search missing required details destination=%s check_in=%s check_out=%s",
            bool(destination),
            bool(check_in),
            bool(check_out),
        )
        return {
            "hotel_options": [],
            "messages": [{"role": "assistant", "content": "Missing hotel search details (destination or check-out date). For one-way trips, please specify the number of nights or a check-out date."}],
        }

    try:
        hotel_stars = trip.get("hotel_stars", [])
        if isinstance(hotel_stars, int):
            hotel_stars = [hotel_stars]
        hotel_stars = [star for star in hotel_stars if star in HOTEL_STARS]

        logger.info(
            "Searching hotels destination=%s check_in=%s check_out=%s travelers=%s stars=%s",
            destination,
            check_in,
            check_out,
            trip.get("num_travelers", 1),
            hotel_stars,
        )
        hotels = api_search_hotels(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=trip.get("num_travelers", 1),
            hotel_stars=hotel_stars,
            currency=trip.get("currency", "EUR"),
        )

        logger.info("Hotel search returned %s options", len(hotels))
        return {
            "hotel_options": hotels,
            "messages": [{"role": "assistant", "content": f"Found {len(hotels)} hotel options."}],
        }
    except Exception as e:
        logger.exception("Hotel search failed")
        return {
            "hotel_options": [],
            "messages": [{"role": "assistant", "content": f"Hotel search failed: {e}"}],
        }


def search_leg_hotels(
    leg: dict,
    trip_request: dict,
) -> list[dict]:
    """Search hotels for a single leg of a multi-city trip.

    Args:
        leg: Leg dict with destination, departure_date (check-in), check_out_date, nights
        trip_request: Full trip request for shared settings (travelers, stars, currency)

    Returns:
        List of hotel options for this leg
    """
    destination = leg.get("destination", "")
    check_in = leg.get("departure_date", "")
    check_out = leg.get("check_out_date", "")

    if not leg.get("needs_hotel"):
        logger.info("Skipping hotel search for leg %s (no hotel needed)", leg.get("leg_index"))
        return []

    if not all([destination, check_in, check_out]):
        logger.warning(
            "Leg hotel search missing required details destination=%s check_in=%s check_out=%s",
            bool(destination), bool(check_in), bool(check_out),
        )
        return []

    try:
        hotel_stars = trip_request.get("hotel_stars", [])
        if isinstance(hotel_stars, int):
            hotel_stars = [hotel_stars]
        hotel_stars = [star for star in hotel_stars if star in HOTEL_STARS]

        logger.info(
            "Searching leg hotels destination=%s check_in=%s check_out=%s nights=%s travelers=%s stars=%s",
            destination, check_in, check_out, leg.get("nights"), trip_request.get("num_travelers", 1), hotel_stars,
        )

        hotels = api_search_hotels(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=trip_request.get("num_travelers", 1),
            hotel_stars=hotel_stars,
            currency=trip_request.get("currency", "EUR"),
        )

        logger.info("Leg hotel search returned %s options for %s", len(hotels), destination)
        return hotels

    except Exception as e:
        logger.exception("Leg hotel search failed for %s", destination)
        return []
