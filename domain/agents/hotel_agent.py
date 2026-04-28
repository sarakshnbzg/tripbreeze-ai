"""Hotel Agent — searches for hotels and formats results for the graph state."""

from constants import HOTEL_STARS
from infrastructure.apis.serpapi_client import search_hotels as api_search_hotels
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _api_hotel_stars(trip: dict) -> list[int]:
    """Only apply star filters upstream when the user explicitly asked for them."""
    if not trip.get("hotel_stars_user_specified"):
        return []

    hotel_stars = trip.get("hotel_stars", [])
    if isinstance(hotel_stars, int):
        hotel_stars = [hotel_stars]
    return [star for star in hotel_stars if star in HOTEL_STARS]


def _preferred_hotel_stars(trip: dict, user_profile: dict) -> list[int]:
    raw = trip.get("hotel_stars") or user_profile.get("preferred_hotel_stars") or []
    if isinstance(raw, int):
        raw = [raw]
    return sorted({int(star) for star in raw if isinstance(star, int) and star in HOTEL_STARS})


def _preferred_hotel_features(preferences: str) -> dict[str, tuple[str, ...]]:
    lowered = str(preferences or "").lower()
    feature_map = {
        "breakfast": ("breakfast",),
        "pool": ("pool",),
        "spa": ("spa",),
        "gym": ("gym", "fitness"),
        "wifi": ("wifi", "wi-fi", "internet"),
        "parking": ("parking",),
        "central location": ("central", "city center", "city centre", "walkable"),
    }
    return {
        label: keywords
        for label, keywords in feature_map.items()
        if any(keyword in lowered for keyword in keywords)
    }


def _hotel_area_text(trip: dict) -> str:
    return str(trip.get("hotel_area") or "").strip().lower()


def _hotel_budget_tier(trip: dict) -> str:
    return str(trip.get("hotel_budget_tier") or "").strip().upper()


def _hotel_text(hotel: dict) -> str:
    amenities = hotel.get("amenities") or []
    amenity_text = " ".join(str(item) for item in amenities)
    return " ".join(
        str(part or "")
        for part in [hotel.get("name"), hotel.get("description"), amenity_text]
    ).lower()


def _rank_hotels_by_preferences(hotels: list[dict], trip: dict, user_profile: dict) -> list[dict]:
    if not hotels:
        return hotels

    preferred_stars = _preferred_hotel_stars(trip, user_profile)
    preferred_features = _preferred_hotel_features(trip.get("preferences", ""))
    preferred_area = _hotel_area_text(trip)
    budget_tier = _hotel_budget_tier(trip)

    ranked: list[dict] = []
    for hotel in hotels:
        score = 0
        reasons: list[str] = []

        hotel_class = hotel.get("hotel_class")
        if isinstance(hotel_class, (int, float)):
            hotel_class = int(hotel_class)
        else:
            hotel_class = None

        if preferred_stars and hotel_class is not None:
            if hotel_class in preferred_stars:
                score += 40
                reasons.append("matches preferred hotel class")
            else:
                distance = min(abs(hotel_class - star) for star in preferred_stars)
                score += max(0, 20 - (distance * 8))

        if budget_tier and hotel_class is not None:
            if budget_tier == "BUDGET":
                if hotel_class <= 3:
                    score += 24
                    reasons.append("fits budget hotel tier")
                elif hotel_class == 4:
                    score += 8
            elif budget_tier == "MID_RANGE":
                if hotel_class in {3, 4}:
                    score += 28
                    reasons.append("fits mid-range hotel tier")
                elif hotel_class in {2, 5}:
                    score += 8
            elif budget_tier == "LUXURY":
                if hotel_class == 5:
                    score += 28
                    reasons.append("fits luxury hotel tier")
                elif hotel_class == 4:
                    score += 12

        rating = hotel.get("rating")
        if isinstance(rating, (int, float)):
            score += int(float(rating) * 3)

        total_price = hotel.get("total_price")
        if isinstance(total_price, (int, float)):
            score += max(0, 24 - int(float(total_price) / 120))

        hotel_text = _hotel_text(hotel)
        if preferred_area and preferred_area in hotel_text:
            score += 30
            reasons.append(f"near {trip.get('hotel_area')}")
        for label, keywords in preferred_features.items():
            if any(keyword in hotel_text for keyword in keywords):
                score += 12
                reasons.append(f"offers {label}")

        ranked_hotel = dict(hotel)
        ranked_hotel["preference_score"] = score
        ranked_hotel["preference_reasons"] = reasons
        ranked.append(ranked_hotel)

    ranked.sort(
        key=lambda hotel: (
            -hotel.get("preference_score", 0),
            hotel.get("total_price", float("inf")),
            -(hotel.get("rating", 0) or 0),
        )
    )
    logger.info("Ranked %s hotel options using explicit preference scoring", len(ranked))
    return ranked


def search_hotels(state: dict) -> dict:
    """LangGraph node: search for hotels based on trip request."""
    trip = state.get("trip_request", {})
    user_profile = state.get("user_profile", {})
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
        hotel_stars = _api_hotel_stars(trip)

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
            hotel_area=trip.get("hotel_area", ""),
            currency=trip.get("currency", "EUR"),
        )
        hotels = _rank_hotels_by_preferences(hotels, trip, user_profile)

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
            "node_errors": [{"node": "hotel_search", "message": str(e)}],
        }


def search_leg_hotels(
    leg: dict,
    trip_request: dict,
    user_profile: dict | None = None,
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
        hotel_stars = _api_hotel_stars(trip_request)

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
            hotel_area=trip_request.get("hotel_area", ""),
            currency=trip_request.get("currency", "EUR"),
        )
        hotels = _rank_hotels_by_preferences(hotels, trip_request, user_profile or {})

        logger.info("Leg hotel search returned %s options for %s", len(hotels), destination)
        return hotels

    except Exception as e:
        logger.exception("Leg hotel search failed for %s", destination)
        return []
