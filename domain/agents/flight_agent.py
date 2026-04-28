"""Flight Agent — searches for flights and formats results for the graph state."""

import re

from settings import MAX_FLIGHT_RESULTS
from infrastructure.apis.serpapi_client import search_flights as api_search_flights, search_return_flights as api_search_return_flights
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _rank_flights_by_preferred_airlines(flights: list[dict], preferred_airlines: list[str]) -> list[dict]:
    """Move flights on preferred airlines to the front while keeping a stable order."""
    if not preferred_airlines:
        return flights

    preferred = [airline.strip().lower() for airline in preferred_airlines if airline.strip()]
    if not preferred:
        return flights

    def is_preferred(flight: dict) -> bool:
        airline_name = str(flight.get("airline", "")).lower()
        return any(
            airline_name == preferred_airline or preferred_airline in airline_name
            for preferred_airline in preferred
        )

    ranked = sorted(flights, key=lambda flight: not is_preferred(flight))
    logger.info(
        "Ranked flight options using %s preferred airlines; matches=%s",
        len(preferred),
        sum(1 for flight in ranked if is_preferred(flight)),
    )
    return ranked


def _normalise_time_window(raw_window: object) -> tuple[int, int] | None:
    if not isinstance(raw_window, list) or len(raw_window) != 2:
        return None
    try:
        start = int(raw_window[0])
        end = int(raw_window[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return None
    if start > end:
        return None
    return start, end


def _extract_departure_hour(raw_time: object) -> int | None:
    if not raw_time:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", str(raw_time))
    if not match:
        return None
    hour = int(match.group(1))
    return hour if 0 <= hour <= 23 else None


def _parse_duration_minutes(raw_duration: object) -> int:
    if isinstance(raw_duration, (int, float)):
        return int(raw_duration)
    text = str(raw_duration or "").strip().lower()
    if not text:
        return 10**9
    hours_match = re.search(r"(\d+)\s*h", text)
    mins_match = re.search(r"(\d+)\s*m", text)
    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(mins_match.group(1)) if mins_match else 0
    total = hours * 60 + minutes
    return total if total > 0 else 10**9


def _flight_price_value(flight: dict) -> float:
    for key in ("price", "total_price"):
        value = flight.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return float("inf")


def _rank_flights_by_preferences(
    flights: list[dict],
    trip_request: dict,
    user_profile: dict,
) -> list[dict]:
    if not flights:
        return flights

    preferred_airlines = [
        airline.strip().lower()
        for airline in user_profile.get("preferred_airlines", [])
        if str(airline).strip()
    ]
    outbound_window = _normalise_time_window(user_profile.get("preferred_outbound_time_window"))

    def airline_match(flight: dict) -> bool:
        airline_name = str(flight.get("airline", "")).lower()
        return any(
            airline_name == preferred_airline or preferred_airline in airline_name
            for preferred_airline in preferred_airlines
        )

    ranked: list[dict] = []
    for flight in flights:
        score = 0
        reasons: list[str] = []

        if preferred_airlines and airline_match(flight):
            score += 40
            reasons.append("matches preferred airline")

        stops = flight.get("stops")
        if isinstance(stops, int):
            score += max(0, 18 - (stops * 8))
            if stops == 0:
                reasons.append("non-stop option")

        departure_hour = _extract_departure_hour(flight.get("departure_time"))
        if outbound_window and departure_hour is not None:
            if outbound_window[0] <= departure_hour <= outbound_window[1]:
                score += 18
                reasons.append("fits preferred departure window")

        price = _flight_price_value(flight)
        max_flight_price = float(trip_request.get("max_flight_price") or 0)
        if max_flight_price > 0 and price <= max_flight_price:
            score += 14
            reasons.append("within flight budget target")

        if price != float("inf"):
            score += max(0, 20 - int(price / 75))

        duration_minutes = _parse_duration_minutes(flight.get("duration"))
        if duration_minutes != 10**9:
            score += max(0, 16 - int(duration_minutes / 120))

        ranked_flight = dict(flight)
        ranked_flight["preference_score"] = score
        ranked_flight["preference_reasons"] = reasons
        ranked.append(ranked_flight)

    ranked.sort(
        key=lambda flight: (
            -flight.get("preference_score", 0),
            _flight_price_value(flight),
            flight.get("stops", 99),
            _parse_duration_minutes(flight.get("duration")),
        )
    )
    logger.info(
        "Ranked %s flight options using explicit preference scoring",
        len(ranked),
    )
    return ranked


def search_flights(state: dict) -> dict:
    """LangGraph node: search for flights based on trip request."""
    trip = state.get("trip_request", {})
    user_profile = state.get("user_profile", {})
    if not trip:
        logger.error("Flight search skipped because trip request is missing")
        return {"flight_options": [], "error": "No trip request found."}

    origin = trip.get("origin", "")
    destination = trip.get("destination", "")
    departure_date = trip.get("departure_date", "")

    if not all([origin, destination, departure_date]):
        logger.warning(
            "Flight search missing required details origin=%s destination=%s departure_date=%s",
            bool(origin),
            bool(destination),
            bool(departure_date),
        )
        return {
            "flight_options": [],
            "messages": [{"role": "assistant", "content": "Missing flight search details (origin, destination, or dates)."}],
        }

    try:
        outbound_time_window = _normalise_time_window(
            user_profile.get("preferred_outbound_time_window")
        )
        return_time_window = _normalise_time_window(
            user_profile.get("preferred_return_time_window")
        )

        stops = trip.get("stops")  # None, 0, 1, or 2

        # Determine max_price: prefer explicit max_flight_price, fall back to
        # deriving from the overall budget (allocate half to flights, per person).
        max_flight_price = trip.get("max_flight_price") or 0
        budget_limit = trip.get("budget_limit") or 0
        num_travelers = trip.get("num_travelers", 1)
        if max_flight_price > 0:
            max_price = int(max_flight_price)
        elif budget_limit > 0:
            max_price = int(budget_limit / num_travelers * 0.5)
        else:
            max_price = None

        max_duration = trip.get("max_duration") or None
        bags = trip.get("bags") or None
        emissions = bool(trip.get("emissions"))
        layover_duration_min = trip.get("layover_duration_min") or None
        layover_duration_max = trip.get("layover_duration_max") or None
        include_airlines = trip.get("include_airlines") or []
        exclude_airlines = trip.get("exclude_airlines") or []

        logger.info(
            "Searching flights origin=%s destination=%s departure=%s return=%s travelers=%s class=%s "
            "outbound_window=%s return_window=%s stops=%s max_price=%s max_duration=%s bags=%s "
            "emissions=%s include_airlines=%s exclude_airlines=%s",
            origin,
            destination,
            departure_date,
            trip.get("return_date"),
            num_travelers,
            trip.get("travel_class", "ECONOMY"),
            outbound_time_window,
            return_time_window,
            stops,
            max_price,
            max_duration,
            bags,
            emissions,
            include_airlines,
            exclude_airlines,
        )
        flights = api_search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=trip.get("return_date"),
            adults=num_travelers,
            travel_class=trip.get("travel_class", "ECONOMY"),
            currency=trip.get("currency", "EUR"),
            outbound_time_window=outbound_time_window,
            return_time_window=return_time_window,
            stops=stops,
            max_price=max_price,
            max_duration=max_duration,
            bags=bags,
            emissions=emissions,
            layover_duration_min=layover_duration_min,
            layover_duration_max=layover_duration_max,
            include_airlines=include_airlines or None,
            exclude_airlines=exclude_airlines or None,
        )
        flights = _rank_flights_by_preferences(flights, trip, user_profile)
        flights = flights[:MAX_FLIGHT_RESULTS]

        logger.info("Flight search returned %s options", len(flights))
        return {
            "flight_options": flights,
            "messages": [{"role": "assistant", "content": f"Found {len(flights)} flight options."}],
        }
    except Exception as e:
        logger.exception("Flight search failed")
        return {
            "flight_options": [],
            "messages": [{"role": "assistant", "content": f"Flight search failed: {e}"}],
            "node_errors": [{"node": "flight_search", "message": str(e)}],
        }


def fetch_return_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    departure_token: str,
    adults: int = 1,
    travel_class: str = "ECONOMY",
    currency: str = "EUR",
    return_time_window: tuple[int, int] | None = None,
) -> list[dict]:
    """Fetch return flight options for a chosen outbound departure token."""
    return api_search_return_flights(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        departure_token=departure_token,
        adults=adults,
        travel_class=travel_class,
        currency=currency,
        return_time_window=return_time_window,
    )


def search_leg_flights(
    leg: dict,
    trip_request: dict,
    user_profile: dict,
) -> list[dict]:
    """Search one-way flights for a single leg of a multi-city trip.

    Args:
        leg: Leg dict with origin, destination, departure_date
        trip_request: Full trip request for shared settings (travelers, class, filters)
        user_profile: User profile for preferred airlines and time windows

    Returns:
        List of flight options for this leg
    """
    origin = leg.get("origin", "")
    destination = leg.get("destination", "")
    departure_date = leg.get("departure_date", "")

    if not all([origin, destination, departure_date]):
        logger.warning(
            "Leg flight search missing required details origin=%s destination=%s departure_date=%s",
            bool(origin), bool(destination), bool(departure_date),
        )
        return []

    try:
        outbound_time_window = _normalise_time_window(
            user_profile.get("preferred_outbound_time_window")
        )
        stops = trip_request.get("stops")
        num_travelers = trip_request.get("num_travelers", 1)

        max_flight_price = trip_request.get("max_flight_price") or 0
        budget_limit = trip_request.get("budget_limit") or 0
        if max_flight_price > 0:
            max_price = int(max_flight_price)
        elif budget_limit > 0:
            max_price = int(budget_limit / num_travelers * 0.3)  # 30% for multi-city (split across legs)
        else:
            max_price = None

        logger.info(
            "Searching leg flights origin=%s destination=%s departure=%s travelers=%s class=%s stops=%s",
            origin, destination, departure_date, num_travelers,
            trip_request.get("travel_class", "ECONOMY"), stops,
        )

        flights = api_search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=None,  # One-way for multi-city legs
            adults=num_travelers,
            travel_class=trip_request.get("travel_class", "ECONOMY"),
            currency=trip_request.get("currency", "EUR"),
            outbound_time_window=outbound_time_window,
            return_time_window=None,
            stops=stops,
            max_price=max_price,
            max_duration=trip_request.get("max_duration") or None,
            bags=trip_request.get("bags") or None,
            emissions=bool(trip_request.get("emissions")),
            layover_duration_min=trip_request.get("layover_duration_min") or None,
            layover_duration_max=trip_request.get("layover_duration_max") or None,
            include_airlines=trip_request.get("include_airlines") or None,
            exclude_airlines=trip_request.get("exclude_airlines") or None,
        )

        flights = _rank_flights_by_preferences(flights, trip_request, user_profile)
        flights = flights[:MAX_FLIGHT_RESULTS]

        logger.info("Leg flight search returned %s options for %s → %s", len(flights), origin, destination)
        return flights

    except Exception as e:
        logger.exception("Leg flight search failed for %s → %s", origin, destination)
        return []
