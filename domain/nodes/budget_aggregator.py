"""Budget Aggregator node — combines costs and checks against the budget limit."""

from config import DAILY_EXPENSE_BY_CURRENCY, DAILY_EXPENSE_BY_DESTINATION, DEFAULT_DAILY_EXPENSE
from domain.utils.dates import trip_duration_days
from infrastructure.currency_utils import currency_prefix
from infrastructure.logging_utils import get_logger
from infrastructure.persistence.memory_store import load_destination_daily_expense

logger = get_logger(__name__)


def _destination_daily_baseline(destination: str) -> tuple[float | None, str]:
    """Return the EUR baseline and source key for a destination."""
    city = (destination or "").lower().strip()

    try:
        db_rate, db_key = load_destination_daily_expense(destination)
    except Exception as exc:
        logger.warning("Destination daily expense DB lookup failed for '%s': %s", destination, exc)
        db_rate, db_key = None, ""

    if db_rate is not None:
        return db_rate, db_key

    for keyword, eur_rate in DAILY_EXPENSE_BY_DESTINATION.items():
        if keyword in city:
            return eur_rate, keyword
    return None, ""


def _destination_daily_rate(destination: str, currency: str) -> float:
    """Return a destination-aware daily expense estimate per adult in the trip's currency.

    Looks up the city in the DB-backed daily-expense table first, then falls back
    to the config-maintained EUR baselines, then scales to the trip currency using
    the ratios already encoded in DAILY_EXPENSE_BY_CURRENCY.  Falls back to the flat
    per-currency rate if the destination is not recognised.
    """
    eur_baseline = DAILY_EXPENSE_BY_CURRENCY.get("EUR", DEFAULT_DAILY_EXPENSE)
    trip_baseline = DAILY_EXPENSE_BY_CURRENCY.get(currency, DEFAULT_DAILY_EXPENSE)
    destination_eur_rate, _source = _destination_daily_baseline(destination)
    if destination_eur_rate is not None:
        return round(destination_eur_rate * (trip_baseline / eur_baseline), 2)
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
    trip_legs = state.get("trip_legs", [])
    budget_limit = trip.get("budget_limit", 0)
    currency = trip.get("currency", "EUR")
    prefix = currency_prefix(currency)
    num_travelers = max(1, int(trip.get("num_travelers", 1) or 1))

    # Multi-city trips: aggregate costs across all legs
    if trip_legs:
        flight_options_by_leg = state.get("flight_options_by_leg", [])
        hotel_options_by_leg = state.get("hotel_options_by_leg", [])

        total_flight_cost = 0.0
        total_hotel_cost = 0.0
        total_daily_expenses = 0.0
        per_leg_breakdown = []

        for leg in trip_legs:
            leg_idx = leg.get("leg_index", 0)
            destination = leg.get("destination", "")
            nights = leg.get("nights", 0)

            # Get flight options for this leg
            leg_flights = flight_options_by_leg[leg_idx] if leg_idx < len(flight_options_by_leg) else []
            leg_flight_cost = min((_flight_total(f) for f in leg_flights), default=0.0)
            total_flight_cost += leg_flight_cost

            # Get hotel options if this leg needs accommodation
            leg_hotel_cost = 0.0
            if leg.get("needs_hotel"):
                leg_hotels = hotel_options_by_leg[leg_idx] if leg_idx < len(hotel_options_by_leg) else []
                leg_hotel_cost = min((h["total_price"] for h in leg_hotels), default=0.0)
                total_hotel_cost += leg_hotel_cost

                # Daily expenses for this destination
                daily_rate = _destination_daily_rate(destination, currency)
                leg_daily = daily_rate * nights * num_travelers
                total_daily_expenses += leg_daily
            else:
                leg_daily = 0.0

            per_leg_breakdown.append({
                "leg_index": leg_idx,
                "origin": leg.get("origin", ""),
                "destination": destination,
                "nights": nights,
                "flight_cost": leg_flight_cost,
                "hotel_cost": leg_hotel_cost,
                "daily_expenses": leg_daily,
                "leg_total": leg_flight_cost + leg_hotel_cost + leg_daily,
            })

        total = total_flight_cost + total_hotel_cost + total_daily_expenses
        within_budget = budget_limit <= 0 or total <= budget_limit

        notes = ""
        if budget_limit > 0 and not within_budget:
            over = total - budget_limit
            notes = (
                f"Estimated total ({prefix}{total:.0f}) exceeds your budget "
                f"({prefix}{budget_limit:.0f}) by {prefix}{over:.0f}. "
                f"Consider cheaper options or fewer destinations."
            )
        elif budget_limit > 0:
            notes = f"You're within budget with ~{prefix}{budget_limit - total:.0f} to spare."

        logger.info(
            "Multi-city budget aggregated legs=%s total_flights=%s total_hotels=%s daily=%s total=%s within_budget=%s",
            len(trip_legs), total_flight_cost, total_hotel_cost, total_daily_expenses, total, within_budget,
        )

        return {
            "budget": {
                "flight_cost": total_flight_cost,
                "hotel_cost": total_hotel_cost,
                "estimated_daily_expenses": total_daily_expenses,
                "total_estimated": total,
                "currency": currency,
                "within_budget": within_budget,
                "budget_notes": notes,
                "per_leg_breakdown": per_leg_breakdown,
                "is_multi_city": True,
            },
            "current_step": "budget_done",
        }

    # Single-destination trip: existing logic
    flights = state.get("flight_options", [])
    hotels = state.get("hotel_options", [])
    budget_limit = trip.get("budget_limit", 0)
    currency = trip.get("currency", "EUR")
    prefix = currency_prefix(currency)

    num_days = trip_duration_days(trip)
    num_travelers = max(1, int(trip.get("num_travelers", 1) or 1))
    destination = trip.get("destination", "")
    _destination_eur_rate, destination_source = _destination_daily_baseline(destination)
    daily_rate = _destination_daily_rate(destination, currency)
    daily_expense_source = destination_source or "default"
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
