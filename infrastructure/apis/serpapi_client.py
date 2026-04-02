"""SerpAPI client — wraps all external travel search calls.

This is the only module that imports `serpapi`. All flight/hotel search
logic in the domain layer calls through here, so swapping providers
means changing only this file.
"""

from serpapi import GoogleSearch

from config import SERPAPI_API_KEY, RAW_FLIGHT_CANDIDATES, MAX_HOTEL_RESULTS, CITY_TO_AIRPORT
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── Flight search ──

TRAVEL_CLASS_MAP = {"ECONOMY": "1", "PREMIUM_ECONOMY": "2", "BUSINESS": "3", "FIRST": "4"}


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    travel_class: str = "ECONOMY",
    currency: str = "EUR",
    outbound_time_window: tuple[int, int] | None = None,
    return_time_window: tuple[int, int] | None = None,
    stops: int | None = None,
    max_price: int | None = None,
    max_duration: int | None = None,
    bags: int | None = None,
    emissions: bool = False,
    layover_duration_min: int | None = None,
    layover_duration_max: int | None = None,
    include_airlines: list[str] | None = None,
    exclude_airlines: list[str] | None = None,
) -> list[dict]:
    """Query Google Flights via SerpAPI and return normalised results."""
    origin = CITY_TO_AIRPORT.get(origin, origin)
    destination = CITY_TO_AIRPORT.get(destination, destination)

    logger.info(
        "SerpAPI flight request origin=%s destination=%s departure=%s return=%s adults=%s class=%s currency=%s outbound_window=%s return_window=%s",
        origin,
        destination,
        departure_date,
        return_date,
        adults,
        travel_class,
        currency,
        outbound_time_window,
        return_time_window,
    )
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "adults": min(adults, 9),
        "travel_class": TRAVEL_CLASS_MAP.get(travel_class, "1"),
        "currency": currency,
        "hl": "en",
        "api_key": SERPAPI_API_KEY,
    }

    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"  # round trip
    else:
        params["type"] = "2"  # one way

    if stops is not None and 0 <= stops <= 2:
        # SerpAPI stops values: 1 = nonstop, 2 = 1 stop or fewer, 3 = 2 stops or fewer
        params["stops"] = stops + 1

    if max_price is not None and max_price > 0:
        params["max_price"] = int(max_price)

    if max_duration and max_duration > 0:
        params["max_duration"] = int(max_duration)

    if bags and bags > 0:
        params["bags"] = int(bags)

    if emissions:
        params["emissions"] = 1

    if layover_duration_min and layover_duration_max and layover_duration_min <= layover_duration_max:
        params["layover_duration"] = f"{layover_duration_min},{layover_duration_max}"

    if include_airlines:
        params["include_airlines"] = ",".join(include_airlines)
    elif exclude_airlines:
        params["exclude_airlines"] = ",".join(exclude_airlines)

    if outbound_time_window and outbound_time_window != (0, 23):
        params["outbound_times"] = f"{outbound_time_window[0]},{outbound_time_window[1]}"
    if return_date and return_time_window and return_time_window != (0, 23):
        params["return_times"] = f"{return_time_window[0]},{return_time_window[1]}"

    results = GoogleSearch(params).get_dict()
    logger.info(
        "SerpAPI flight response best_flights=%s other_flights=%s",
        len(results.get("best_flights", [])),
        len(results.get("other_flights", [])),
    )

    raw_groups = results.get("best_flights", []) + results.get("other_flights", [])
    flights = []

    for group in raw_groups[:RAW_FLIGHT_CANDIDATES]:
        legs = group.get("flights", [])
        if not legs:
            continue

        first_leg, last_leg = legs[0], legs[-1]
        total_duration = group.get("total_duration", 0)
        dep = first_leg.get("departure_airport", {})
        arr = last_leg.get("arrival_airport", {})

        flights.append({
            "airline": first_leg.get("airline", ""),
            "departure_time": dep.get("time", ""),
            "arrival_time": arr.get("time", ""),
            "duration": f"{total_duration // 60}h {total_duration % 60}m",
            "stops": len(legs) - 1,
            "price": group.get("price", 0),
            "currency": currency,
            "outbound_summary": (
                f"{dep.get('id', '?')} {dep.get('time', '?')} → "
                f"{arr.get('id', '?')} {arr.get('time', '?')}"
            ),
            "return_summary": "",
        })

    logger.info("Normalised %s raw flight candidates", len(flights))
    return flights


# ── Hotel search ──

STAR_TO_RATING = {1: "", 2: "", 3: "7", 4: "8", 5: "9"}


def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    hotel_stars: list[int] | None = None,
    currency: str = "EUR",
) -> list[dict]:
    """Query Google Hotels via SerpAPI and return normalised results."""
    from datetime import datetime

    hotel_stars = sorted(hotel_stars or [])
    min_selected_star = min(hotel_stars) if hotel_stars else None

    logger.info(
        "SerpAPI hotel request destination=%s check_in=%s check_out=%s adults=%s stars=%s currency=%s",
        destination,
        check_in,
        check_out,
        adults,
        hotel_stars,
        currency,
    )
    params = {
        "engine": "google_hotels",
        "q": f"hotels in {destination}",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": min(adults, 9),
        "currency": currency,
        "hl": "en",
        "gl": "us",
        "api_key": SERPAPI_API_KEY,
    }

    min_rating = STAR_TO_RATING.get(min_selected_star, "")
    if min_rating:
        params["min_rating"] = min_rating

    results = GoogleSearch(params).get_dict()
    properties = results.get("properties", [])
    logger.info("SerpAPI hotel response properties=%s", len(properties))

    d1 = datetime.strptime(check_in, "%Y-%m-%d")
    d2 = datetime.strptime(check_out, "%Y-%m-%d")
    nights = (d2 - d1).days or 1

    hotels = []
    for prop in properties[:MAX_HOTEL_RESULTS]:
        hotel_class = prop.get("hotel_class")
        if hotel_class is None:
            hotel_class = prop.get("extracted_hotel_class")
        try:
            hotel_class = int(round(float(hotel_class))) if hotel_class is not None else None
        except (TypeError, ValueError):
            hotel_class = None

        if hotel_stars and hotel_class is not None and hotel_class not in hotel_stars:
            continue

        total_price = prop.get("total_rate", {}).get("extracted_lowest", 0)
        if not total_price:
            per_night = prop.get("rate_per_night", {}).get("extracted_lowest", 0)
            total_price = per_night * nights

        hotels.append({
            "name": prop.get("name", "Unknown Hotel"),
            "address": prop.get("description", ""),
            "hotel_class": hotel_class,
            "rating": prop.get("overall_rating", 0),
            "price_per_night": round(total_price / nights, 2) if nights else total_price,
            "total_price": total_price,
            "currency": currency,
            "amenities": prop.get("amenities", []),
            "check_in": check_in,
            "check_out": check_out,
        })
        if len(hotels) >= MAX_HOTEL_RESULTS:
            break

    logger.info("Normalised %s hotel options", len(hotels))
    return hotels
