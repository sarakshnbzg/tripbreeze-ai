"""Budget Aggregator node — combines costs and checks against the budget limit."""

from datetime import datetime

from config import DEFAULT_DAILY_EXPENSE
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _currency_prefix(currency: str) -> str:
    return {
        "EUR": "EUR ",
        "USD": "$",
        "GBP": "GBP ",
        "CAD": "CAD ",
        "AUD": "AUD ",
        "JPY": "JPY ",
        "CHF": "CHF ",
        "SGD": "SGD ",
        "AED": "AED ",
        "NZD": "NZD ",
    }.get(currency.upper(), f"{currency.upper()} ")


def _trip_days(trip: dict) -> int:
    try:
        d1 = datetime.strptime(trip.get("departure_date", ""), "%Y-%m-%d")
        d2 = datetime.strptime(trip.get("return_date", ""), "%Y-%m-%d")
        return (d2 - d1).days or 1
    except ValueError:
        return 1


def _filter_options_within_budget(
    flights: list[dict],
    hotels: list[dict],
    budget_limit: float,
    estimated_daily_total: float,
) -> tuple[list[dict], list[dict]]:
    """Keep only options that can form at least one within-budget trip combination."""
    if budget_limit <= 0:
        return flights, hotels

    cheapest_flight = min((f["price"] for f in flights), default=None)
    cheapest_hotel = min((h["total_price"] for h in hotels), default=None)

    filtered_flights = [
        flight
        for flight in flights
        if cheapest_hotel is not None and flight["price"] + cheapest_hotel + estimated_daily_total <= budget_limit
    ]
    filtered_hotels = [
        hotel
        for hotel in hotels
        if cheapest_flight is not None and hotel["total_price"] + cheapest_flight + estimated_daily_total <= budget_limit
    ]

    return filtered_flights, filtered_hotels


def budget_aggregator(state: dict) -> dict:
    """LangGraph node: aggregate flight + hotel costs and compare to budget."""
    trip = state.get("trip_request", {})
    flights = state.get("flight_options", [])
    hotels = state.get("hotel_options", [])
    budget_limit = trip.get("budget_limit", 0)
    currency = trip.get("currency", "EUR")
    currency_prefix = _currency_prefix(currency)

    num_days = _trip_days(trip)
    estimated_daily_total = DEFAULT_DAILY_EXPENSE * num_days
    filtered_flights, filtered_hotels = _filter_options_within_budget(
        flights,
        hotels,
        budget_limit,
        estimated_daily_total,
    )

    flight_cost = min((f["price"] for f in filtered_flights), default=0.0)
    hotel_cost = min((h["total_price"] for h in filtered_hotels), default=0.0)
    total = flight_cost + hotel_cost + estimated_daily_total
    has_viable_combination = bool(filtered_flights) and bool(filtered_hotels)
    within_budget = budget_limit <= 0 or (has_viable_combination and total <= budget_limit)

    notes = ""
    if budget_limit > 0 and not has_viable_combination:
        notes = (
            "No flight and hotel combinations fit the selected budget. "
            "Try increasing the budget, shortening the trip, or changing the dates."
        )
    elif budget_limit > 0 and not within_budget:
        over = total - budget_limit
        notes = (
            f"Estimated total ({currency_prefix}{total:.0f}) exceeds your budget "
            f"({currency_prefix}{budget_limit:.0f}) by {currency_prefix}{over:.0f}. "
            f"Consider a cheaper flight/hotel or shorter stay."
        )
    elif budget_limit > 0:
        notes = f"You're within budget with ~{currency_prefix}{budget_limit - total:.0f} to spare."

    logger.info(
        "Budget aggregated flights_before=%s flights_after=%s hotels_before=%s hotels_after=%s daily_estimate=%s flight_cost=%s hotel_cost=%s total=%s within_budget=%s",
        len(flights),
        len(filtered_flights),
        len(hotels),
        len(filtered_hotels),
        estimated_daily_total,
        flight_cost,
        hotel_cost,
        total,
        within_budget,
    )

    return {
        "flight_options": filtered_flights,
        "hotel_options": filtered_hotels,
        "budget": {
            "flights_before_budget_filter": len(flights),
            "flights_after_budget_filter": len(filtered_flights),
            "hotels_before_budget_filter": len(hotels),
            "hotels_after_budget_filter": len(filtered_hotels),
            "flight_cost": flight_cost,
            "hotel_cost": hotel_cost,
            "estimated_daily_expenses": estimated_daily_total,
            "total_estimated": total,
            "currency": currency,
            "within_budget": within_budget,
            "budget_notes": notes,
        },
        "current_step": "budget_done",
    }
