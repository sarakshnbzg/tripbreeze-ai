"""Budget Aggregator node — combines costs and checks against the budget limit."""

from config import DAILY_EXPENSE_BY_CURRENCY, DAILY_EXPENSE_BY_DESTINATION, DEFAULT_DAILY_EXPENSE
from domain.utils.dates import trip_duration_days
from infrastructure.currency_utils import currency_prefix
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _destination_daily_rate(destination: str, currency: str) -> float:
    """Return a destination-aware daily expense estimate per adult in the trip's currency.

    Looks up the city in DAILY_EXPENSE_BY_DESTINATION (EUR-equivalent mid-range baselines
    derived from knowledge_base/destinations.md), then scales to the trip currency using
    the ratios already encoded in DAILY_EXPENSE_BY_CURRENCY.  Falls back to the flat
    per-currency rate if the destination is not recognised.
    """
    city = (destination or "").lower().strip()
    eur_baseline = DAILY_EXPENSE_BY_CURRENCY.get("EUR", DEFAULT_DAILY_EXPENSE)
    trip_baseline = DAILY_EXPENSE_BY_CURRENCY.get(currency, DEFAULT_DAILY_EXPENSE)
    for keyword, eur_rate in DAILY_EXPENSE_BY_DESTINATION.items():
        if keyword in city:
            return round(eur_rate * (trip_baseline / eur_baseline), 2)
    return trip_baseline


def _flight_total(flight: dict) -> float:
    """Return the total price for all passengers on a flight."""
    return flight.get("total_price", flight["price"])


def _filter_options_within_budget(
    flights: list[dict],
    hotels: list[dict],
    budget_limit: float,
    estimated_daily_total: float,
) -> tuple[list[dict], list[dict]]:
    """Keep only options that can form at least one within-budget trip combination."""
    if budget_limit <= 0:
        return flights, hotels

    cheapest_flight = min((_flight_total(f) for f in flights), default=None)
    cheapest_hotel = min((h["total_price"] for h in hotels), default=None)

    filtered_flights = [
        flight
        for flight in flights
        if cheapest_hotel is not None and _flight_total(flight) + cheapest_hotel + estimated_daily_total <= budget_limit
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
    prefix = currency_prefix(currency)

    num_days = trip_duration_days(trip)
    num_travelers = max(1, int(trip.get("num_travelers", 1) or 1))
    destination = trip.get("destination", "")
    daily_rate = _destination_daily_rate(destination, currency)
    city = destination.lower().strip()
    daily_expense_source = next(
        (kw for kw in DAILY_EXPENSE_BY_DESTINATION if kw in city), "default"
    )
    estimated_daily_total = daily_rate * num_days * num_travelers
    filtered_flights, filtered_hotels = _filter_options_within_budget(
        flights,
        hotels,
        budget_limit,
        estimated_daily_total,
    )

    flight_cost = min((_flight_total(f) for f in filtered_flights), default=0.0)
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
            f"Estimated total ({prefix}{total:.0f}) exceeds your budget "
            f"({prefix}{budget_limit:.0f}) by {prefix}{over:.0f}. "
            f"Consider a cheaper flight/hotel or shorter stay."
        )
    elif budget_limit > 0:
        notes = f"You're within budget with ~{prefix}{budget_limit - total:.0f} to spare."

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
            "daily_expense_per_traveler": daily_rate,
            "daily_expense_days": num_days,
            "daily_expense_travelers": num_travelers,
            "daily_expense_source": daily_expense_source,
            "total_estimated": total,
            "currency": currency,
            "within_budget": within_budget,
            "budget_notes": notes,
        },
        "current_step": "budget_done",
    }
