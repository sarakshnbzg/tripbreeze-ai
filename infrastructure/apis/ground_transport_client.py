"""Ground transport client — stub implementation returning realistic mock data.

This is a placeholder for a real provider (Rome2Rio, Google Routes, etc.).
Replace the body of `search_ground_transport` to swap in a real API; the
return shape is the contract the rest of the app depends on.

Booking URLs deep-link to Google Maps transit directions, which is
free, no-API-key, and gives users real live schedules and booking paths.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote_plus

from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

MODE_CATALOG: dict[str, dict] = {
    "train": {"operators": ["Eurostar", "SNCF", "Deutsche Bahn", "Trenitalia", "Renfe"], "speed_kmh": 200},
    "bus": {"operators": ["FlixBus", "BlaBlaCar Bus", "Greyhound", "National Express"], "speed_kmh": 80},
    "ferry": {"operators": ["Stena Line", "DFDS", "P&O Ferries"], "speed_kmh": 40},
}


def _google_maps_transit_url(origin: str, destination: str, departure_date: str) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(origin)}"
        f"&destination={quote_plus(destination)}"
        f"&travelmode=transit"
    )


def _estimate_distance_km(origin: str, destination: str) -> int:
    """Deterministic pseudo-distance from origin/destination names."""
    seed = sum(ord(c) for c in f"{origin.lower()}{destination.lower()}")
    return 150 + (seed % 900)


def _format_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"


def _format_time(base: datetime, offset_minutes: int) -> str:
    return (base + timedelta(minutes=offset_minutes)).strftime("%H:%M")


def search_ground_transport(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    currency: str = "EUR",
) -> list[dict]:
    """Return mock ground-transport options between two cities on a given date.

    Shape mirrors flight_options: operator, departure_time, arrival_time,
    duration, price, total_price, currency, booking_url, plus mode-specific
    fields (mode, segments).
    """
    if not origin or not destination or not departure_date:
        logger.warning(
            "Ground transport search skipped origin=%s destination=%s date=%s",
            bool(origin), bool(destination), bool(departure_date),
        )
        return []

    try:
        base = datetime.strptime(departure_date, "%Y-%m-%d").replace(hour=8, minute=0)
    except ValueError:
        logger.warning("Invalid departure_date for ground transport: %s", departure_date)
        return []

    distance_km = _estimate_distance_km(origin, destination)
    logger.info(
        "Ground transport stub origin=%s destination=%s date=%s distance_est=%skm",
        origin, destination, departure_date, distance_km,
    )

    options: list[dict] = []
    booking_url = _google_maps_transit_url(origin, destination, departure_date)

    # Train option — fastest ground mode for plausible distances
    if 80 <= distance_km <= 1500:
        train_minutes = int(distance_km / MODE_CATALOG["train"]["speed_kmh"] * 60)
        train_price_pp = round(0.12 * distance_km, 2)
        options.append({
            "mode": "train",
            "operator": MODE_CATALOG["train"]["operators"][distance_km % len(MODE_CATALOG["train"]["operators"])],
            "departure_time": _format_time(base, 0),
            "arrival_time": _format_time(base, train_minutes),
            "duration": _format_duration(train_minutes),
            "stops": 0 if distance_km < 400 else 1,
            "segments_summary": f"{origin} → {destination} (direct)" if distance_km < 400 else f"{origin} → transfer → {destination}",
            "price": train_price_pp,
            "total_price": round(train_price_pp * adults, 2),
            "adults": adults,
            "currency": currency,
            "booking_url": booking_url,
        })

    # Bus option — cheapest, available for most overland routes
    if 50 <= distance_km <= 1200:
        bus_minutes = int(distance_km / MODE_CATALOG["bus"]["speed_kmh"] * 60)
        bus_price_pp = round(0.05 * distance_km, 2)
        options.append({
            "mode": "bus",
            "operator": MODE_CATALOG["bus"]["operators"][distance_km % len(MODE_CATALOG["bus"]["operators"])],
            "departure_time": _format_time(base, 120),
            "arrival_time": _format_time(base, 120 + bus_minutes),
            "duration": _format_duration(bus_minutes),
            "stops": 1 if distance_km < 500 else 2,
            "segments_summary": f"{origin} → {destination} (coach)",
            "price": bus_price_pp,
            "total_price": round(bus_price_pp * adults, 2),
            "adults": adults,
            "currency": currency,
            "booking_url": booking_url,
        })

    # Ferry option — only for shorter coastal-feeling routes
    if 100 <= distance_km <= 400 and (distance_km % 3 == 0):
        ferry_minutes = int(distance_km / MODE_CATALOG["ferry"]["speed_kmh"] * 60)
        ferry_price_pp = round(0.18 * distance_km, 2)
        options.append({
            "mode": "ferry",
            "operator": MODE_CATALOG["ferry"]["operators"][distance_km % len(MODE_CATALOG["ferry"]["operators"])],
            "departure_time": _format_time(base, 240),
            "arrival_time": _format_time(base, 240 + ferry_minutes),
            "duration": _format_duration(ferry_minutes),
            "stops": 0,
            "segments_summary": f"{origin} port → {destination} port",
            "price": ferry_price_pp,
            "total_price": round(ferry_price_pp * adults, 2),
            "adults": adults,
            "currency": currency,
            "booking_url": booking_url,
        })

    logger.info("Ground transport stub returned %s options", len(options))
    return options
