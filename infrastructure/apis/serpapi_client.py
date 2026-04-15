"""SerpAPI client — wraps all external travel search calls.

This is the only module that imports `serpapi`. All flight/hotel search
logic in the domain layer calls through here, so swapping providers
means changing only this file.
"""

from datetime import datetime
from urllib.parse import quote_plus
import re

from serpapi import GoogleSearch

from config import SERPAPI_API_KEY, RAW_FLIGHT_CANDIDATES, MAX_FLIGHT_RESULTS, MAX_HOTEL_RESULTS, CITY_TO_AIRPORT, DESTINATIONS
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── Flight search ──

TRAVEL_CLASS_MAP = {"ECONOMY": "1", "PREMIUM_ECONOMY": "2", "BUSINESS": "3", "FIRST": "4"}


def _build_google_flights_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None,
    adults: int,
    travel_class: str,
) -> str:
    """Build a user-facing Google Flights search URL pre-filled with the query."""
    query_parts = [f"Flights from {origin} to {destination} on {departure_date}"]
    if return_date:
        query_parts.append(f"returning {return_date}")
    if adults > 1:
        query_parts.append(f"for {adults} adults")
    cls = travel_class.replace("_", " ").lower()
    if cls and cls != "economy":
        query_parts.append(cls)
    return f"https://www.google.com/travel/flights?q={quote_plus(' '.join(query_parts))}"


def _format_flight_legs_summary(legs: list[dict]) -> str:
    """Create a compact route/time summary from a SerpAPI flight leg list."""
    if not legs:
        return ""

    first_leg, last_leg = legs[0], legs[-1]
    dep = first_leg.get("departure_airport", {})
    arr = last_leg.get("arrival_airport", {})
    return (
        f"{dep.get('id', '?')} {dep.get('time', '?')} → "
        f"{arr.get('id', '?')} {arr.get('time', '?')}"
    )


def _extract_inline_return_legs(group: dict) -> list[dict]:
    """Return inline return-leg data when a provider includes it in the result."""
    for key in ("return_flights", "returning_flights", "return_flight"):
        value = group.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _base_flight_params(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None,
    adults: int,
    travel_class: str,
    currency: str,
) -> dict:
    """Build shared Google Flights params for initial and token-based searches."""
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

    return params


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
    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "Flight search requires `SERPAPI_API_KEY` in your environment or Streamlit secrets."
        )

    if origin not in CITY_TO_AIRPORT:
        logger.warning("Origin city '%s' not found in airport mapping — passing as-is", origin)
    if destination not in CITY_TO_AIRPORT:
        logger.warning("Destination city '%s' not found in airport mapping — passing as-is", destination)
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
    params = _base_flight_params(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        travel_class=travel_class,
        currency=currency,
    )

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

    try:
        results = GoogleSearch(params).get_dict()
    except Exception as exc:
        logger.error("SerpAPI flight search failed: %s", exc)
        return []

    logger.info(
        "SerpAPI flight response best_flights=%s other_flights=%s",
        len(results.get("best_flights", [])),
        len(results.get("other_flights", [])),
    )

    raw_groups = results.get("best_flights", []) + results.get("other_flights", [])
    flights = []

    google_flights_url = _build_google_flights_url(
        origin, destination, departure_date, return_date, adults, travel_class
    )

    for group in raw_groups[:RAW_FLIGHT_CANDIDATES]:
        legs = group.get("flights", [])
        if not legs:
            continue

        first_leg, last_leg = legs[0], legs[-1]
        total_duration = group.get("total_duration", 0)
        dep = first_leg.get("departure_airport", {})
        arr = last_leg.get("arrival_airport", {})
        inline_return_legs = _extract_inline_return_legs(group)
        return_summary = _format_flight_legs_summary(inline_return_legs)
        if return_date and not return_summary:
            return_summary = (
                "Return details require selecting this outbound option "
                "with Google Flights."
            )

        # SerpAPI returns total price for all passengers; normalise to per-person
        raw_price = group.get("price", 0)
        price_per_person = round(raw_price / adults, 2) if adults > 1 else raw_price

        flights.append({
            "airline": first_leg.get("airline", ""),
            "departure_time": dep.get("time", ""),
            "arrival_time": arr.get("time", ""),
            "duration": f"{total_duration // 60}h {total_duration % 60}m",
            "stops": len(legs) - 1,
            "price": price_per_person,
            "total_price": raw_price,
            "adults": adults,
            "currency": currency,
            "outbound_summary": (
                _format_flight_legs_summary(legs)
            ),
            "return_summary": return_summary,
            "return_details_available": bool(inline_return_legs),
            "departure_token": group.get("departure_token", ""),
            "booking_url": google_flights_url,
        })

    logger.info("Normalised %s raw flight candidates", len(flights))
    return flights


def search_return_flights(
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
    """Use an outbound `departure_token` to fetch return-flight options."""
    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "Return flight search requires `SERPAPI_API_KEY` in your environment or Streamlit secrets."
        )

    if not return_date or not departure_token:
        logger.warning(
            "Return flight search skipped return_date_present=%s departure_token_present=%s",
            bool(return_date),
            bool(departure_token),
        )
        return []

    origin = CITY_TO_AIRPORT.get(origin, origin)
    destination = CITY_TO_AIRPORT.get(destination, destination)

    params = _base_flight_params(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        travel_class=travel_class,
        currency=currency,
    )
    params["departure_token"] = departure_token

    if return_time_window and return_time_window != (0, 23):
        params["return_times"] = f"{return_time_window[0]},{return_time_window[1]}"

    try:
        results = GoogleSearch(params).get_dict()
    except Exception as exc:
        logger.error("SerpAPI return flight search failed: %s", exc)
        return []

    raw_groups = results.get("best_flights", []) + results.get("other_flights", [])
    return_options = []
    for group in raw_groups[:MAX_FLIGHT_RESULTS]:
        legs = group.get("flights", [])
        if not legs:
            continue

        first_leg, last_leg = legs[0], legs[-1]
        total_duration = group.get("total_duration", 0)
        dep = first_leg.get("departure_airport", {})
        arr = last_leg.get("arrival_airport", {})
        raw_price = group.get("price", 0)
        price_per_person = round(raw_price / adults, 2) if adults > 1 else raw_price

        return_options.append({
            "airline": first_leg.get("airline", ""),
            "departure_time": dep.get("time", ""),
            "arrival_time": arr.get("time", ""),
            "duration": f"{total_duration // 60}h {total_duration % 60}m",
            "stops": len(legs) - 1,
            "price": price_per_person,
            "total_price": raw_price,
            "adults": adults,
            "currency": currency,
            "return_summary": _format_flight_legs_summary(legs),
            "booking_token": group.get("booking_token", ""),
        })

    logger.info("Normalised %s return flight candidates", len(return_options))
    return return_options


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
    if not SERPAPI_API_KEY:
        raise RuntimeError(
            "Hotel search requires `SERPAPI_API_KEY` in your environment or Streamlit secrets."
        )

    if destination not in CITY_TO_AIRPORT and destination not in DESTINATIONS:
        logger.warning("Hotel destination '%s' not found in known destinations — passing as-is", destination)

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

    try:
        results = GoogleSearch(params).get_dict()
    except Exception as exc:
        logger.error("SerpAPI hotel search failed: %s", exc)
        return []

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
        # SerpAPI may return hotel_class as an int, a float string ("4.0"),
        # or a string like "3-star hotel" — extract the leading digit in all cases.
        if hotel_class is not None:
            try:
                hotel_class = int(round(float(hotel_class)))
            except (TypeError, ValueError):
                m = re.search(r"(\d+)", str(hotel_class))
                hotel_class = int(m.group(1)) if m else None
        if hotel_class is not None and not (1 <= hotel_class <= 5):
            hotel_class = None

        if hotel_stars and hotel_class is not None and hotel_class not in hotel_stars:
            continue

        total_price = prop.get("total_rate", {}).get("extracted_lowest", 0)
        if not total_price:
            per_night = prop.get("rate_per_night", {}).get("extracted_lowest", 0)
            total_price = per_night * nights

        hotel_name = prop.get("name", "Unknown Hotel")
        booking_url = prop.get("link") or (
            f"https://www.google.com/travel/hotels/"
            f"{quote_plus(destination)}"
            f"?q={quote_plus(hotel_name)}"
            f"&check_in={check_in}&check_out={check_out}"
        )

        hotels.append({
            "name": hotel_name,
            "description": prop.get("description", ""),
            "address": prop.get("address", ""),
            "property_token": prop.get("property_token", ""),
            "hotel_class": hotel_class,
            "rating": prop.get("overall_rating", 0),
            "price_per_night": round(total_price / nights, 2) if nights else total_price,
            "total_price": total_price,
            "currency": currency,
            "amenities": prop.get("amenities", []),
            "check_in": check_in,
            "check_out": check_out,
            "booking_url": booking_url,
        })
        if len(hotels) >= MAX_HOTEL_RESULTS:
            break

    logger.info("Normalised %s hotel options", len(hotels))
    return hotels


def fetch_hotel_address(
    property_token: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    currency: str = "EUR",
) -> str:
    """Look up a hotel's street address via the Google Hotels property-details endpoint.

    Returns an empty string if the lookup fails or no address is present.
    """
    if not SERPAPI_API_KEY or not property_token:
        return ""

    params = {
        "engine": "google_hotels",
        "property_token": property_token,
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": min(adults, 9),
        "currency": currency,
        "hl": "en",
        "gl": "us",
        "api_key": SERPAPI_API_KEY,
    }

    try:
        details = GoogleSearch(params).get_dict()
    except Exception as exc:
        logger.error("SerpAPI hotel details lookup failed: %s", exc)
        return ""

    return details.get("address", "") or ""


# ── Attractions / places search ──

INTEREST_QUERIES: dict[str, list[str]] = {
    "food": ["top restaurants", "local food"],
    "history": ["historical landmarks", "museums"],
    "nature": ["parks and gardens", "scenic viewpoints"],
    "art": ["art museums", "galleries"],
    "nightlife": ["bars and clubs"],
    "shopping": ["shopping areas", "markets"],
    "outdoors": ["outdoor activities", "hikes"],
    "family": ["family attractions", "kid-friendly activities"],
}


def search_attractions(
    destination: str,
    interests: list[str] | None = None,
    max_per_query: int = 6,
    max_total: int = 24,
) -> list[dict]:
    """Search Google Maps via SerpAPI for attractions matching the user's interests.

    Falls back to a generic "top attractions" query if no interests are provided.
    Returns a deduplicated list of {name, category, address, rating, reviews}.
    """
    if not SERPAPI_API_KEY:
        logger.warning("search_attractions skipped — no SERPAPI_API_KEY configured")
        return []
    if not destination:
        return []

    interests = [i for i in (interests or []) if i in INTEREST_QUERIES]
    if interests:
        queries: list[tuple[str, str]] = []
        for interest in interests:
            for sub in INTEREST_QUERIES[interest]:
                queries.append((interest, sub))
    else:
        queries = [("general", "top attractions")]

    logger.info(
        "SerpAPI attractions request destination=%s interests=%s queries=%s",
        destination,
        interests,
        [q for _, q in queries],
    )

    seen_names: set[str] = set()
    results: list[dict] = []

    for category, sub_query in queries:
        params = {
            "engine": "google_maps",
            "q": f"{sub_query} in {destination}",
            "type": "search",
            "hl": "en",
            "api_key": SERPAPI_API_KEY,
        }
        try:
            payload = GoogleSearch(params).get_dict()
        except Exception as exc:
            logger.error("SerpAPI attractions search failed for '%s': %s", sub_query, exc)
            continue

        local_results = payload.get("local_results") or []
        if isinstance(local_results, dict):
            local_results = local_results.get("places", []) or []

        for place in local_results[:max_per_query]:
            name = place.get("title") or place.get("name")
            if not name:
                continue
            key = name.lower().strip()
            if key in seen_names:
                continue
            seen_names.add(key)
            results.append({
                "name": name,
                "category": category,
                "address": place.get("address", ""),
                "rating": place.get("rating"),
                "reviews": place.get("reviews"),
                "description": place.get("description", "") or place.get("type", ""),
            })
            if len(results) >= max_total:
                break
        if len(results) >= max_total:
            break

    logger.info("Normalised %s attraction candidates", len(results))
    return results
