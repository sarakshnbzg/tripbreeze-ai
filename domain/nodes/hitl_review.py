"""HITL Review node — formats research results for human inspection."""

from application.state import TravelState
from application.workflow_types import WorkflowStep
from domain.utils.dates import trip_duration_display
from infrastructure.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def _markdown_table_value(value: object) -> str:
    """Keep dynamic values safe inside Markdown table cells."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _format_flight_filters(trip: dict) -> str:
    filters: list[str] = []

    class_name = str(trip.get("travel_class", "ECONOMY")).replace("_", " ").title()
    if class_name:
        filters.append(f"Cabin: {class_name}")

    max_duration = int(trip.get("max_duration") or 0)
    if max_duration > 0:
        hours = max_duration // 60
        minutes = max_duration % 60
        duration_label = f"{hours}h" if minutes == 0 else f"{hours}h {minutes}m"
        filters.append(f"Max duration: {duration_label}")

    stops = trip.get("stops")
    if isinstance(stops, int):
        filters.append("Direct only" if stops == 0 else f"Up to {stops} stop{'s' if stops != 1 else ''}")

    exclude_airlines = [str(code).strip() for code in trip.get("exclude_airlines", []) if str(code).strip()]
    if exclude_airlines:
        filters.append(f"Exclude: {', '.join(exclude_airlines)}")

    include_airlines = [str(code).strip() for code in trip.get("include_airlines", []) if str(code).strip()]
    if include_airlines:
        filters.append(f"Only: {', '.join(include_airlines)}")

    if not filters:
        return ""

    return "\n".join(
        [
            "### Flight Filters",
            "",
            "| Filter | Value |",
            "|:---|:---|",
            *[
                f"| Applied | {_markdown_table_value(value)} |"
                for value in filters
            ],
        ]
    )


def _format_multi_city_summary(trip: dict, trip_legs: list[dict]) -> str:
    """Format a summary for multi-city trips."""
    legs_route = " → ".join(
        leg.get("destination", "?") for leg in trip_legs
    )
    full_route = f"{trip.get('origin', '?')} → {legs_route}"

    total_nights = sum(leg.get("nights", 0) for leg in trip_legs)
    travelers = trip.get("num_travelers", 1)
    class_name = str(trip.get("travel_class", "ECONOMY")).replace("_", " ").title()

    rows = [
        "### Multi-City Trip Summary",
        "",
        "| Detail | Selection |",
        "|:---|:---|",
        f"| Route | {_markdown_table_value(full_route)} |",
        f"| Legs | {_markdown_table_value(len(trip_legs))} |",
        f"| Total nights | {_markdown_table_value(total_nights)} |",
        f"| Travelers | {_markdown_table_value(travelers)} |",
        f"| Cabin class | {_markdown_table_value(class_name)} |",
        "",
        "#### Leg Details",
        "",
        "| Leg | Route | Date | Nights |",
        "|:---|:---|:---|:---|",
    ]

    for leg in trip_legs:
        leg_num = leg.get("leg_index", 0) + 1
        route = f"{leg.get('origin', '?')} → {leg.get('destination', '?')}"
        date = leg.get("departure_date", "?")
        nights = leg.get("nights", 0)
        nights_str = f"{nights} night(s)" if nights > 0 else "Return"
        rows.append(f"| {leg_num} | {_markdown_table_value(route)} | {_markdown_table_value(date)} | {_markdown_table_value(nights_str)} |")

    return "\n".join(rows)


def _format_trip_summary(trip: dict, flights: list[dict], hotels: list[dict]) -> str:
    route = f"{trip.get('origin', '?')} -> {trip.get('destination', '?')}"
    if trip.get("return_date"):
        dates = f"{trip.get('departure_date', '?')} to {trip.get('return_date', '?')}"
        trip_type = "Round trip"
    else:
        dates = f"{trip.get('departure_date', '?')} (one-way)"
        trip_type = "One-way"
    travelers = trip.get("num_travelers", 1)
    class_name = str(trip.get("travel_class", "ECONOMY")).replace("_", " ").title()
    nights = trip_duration_display(trip)

    return "\n".join(
        [
            "### Trip Summary",
            "",
            "| Detail | Selection |",
            "|:---|:---|",
            f"| Route | {_markdown_table_value(route)} |",
            f"| Trip type | {_markdown_table_value(trip_type)} |",
            f"| Dates | {_markdown_table_value(dates)} |",
            f"| Nights | {_markdown_table_value(nights)} |",
            f"| Travelers | {_markdown_table_value(travelers)} |",
            f"| Cabin class | {_markdown_table_value(class_name)} |",
        ]
    )


def hitl_review(state: TravelState) -> dict:
    """Prepare the review summary for the user to approve or adjust."""
    flights = state.get("flight_options", [])
    hotels = state.get("hotel_options", [])
    trip_legs = state.get("trip_legs", [])
    budget = state.get("budget", {})
    dest_info = state.get("destination_info", "")
    rag_used = state.get("rag_used", False)
    rag_sources = state.get("rag_sources", [])
    trip = state.get("trip_request", {})

    is_multi_city = bool(trip_legs)
    logger.info(
        "Preparing HITL review with %s flights, %s hotels, budget_present=%s, destination_info_present=%s, multi_city=%s legs=%s",
        len(flights),
        len(hotels),
        bool(budget),
        bool(dest_info),
        is_multi_city,
        len(trip_legs) if is_multi_city else 0,
    )
    log_event(
        logger,
        "workflow.review_ready",
        flight_option_count=len(flights),
        hotel_option_count=len(hotels),
        has_budget=bool(budget),
        has_destination_info=bool(dest_info),
        is_multi_city=is_multi_city,
        trip_leg_count=len(trip_legs) if is_multi_city else 0,
    )

    parts = []

    if dest_info:
        heading = "### Destination Briefing"
        if rag_used:
            source_list = ", ".join(rag_sources) if rag_sources else "local knowledge base"
            heading += f"\n\n_Source: {source_list}_"
        parts.append(f"{heading}\n\n{dest_info}")
    elif rag_used:
        parts.append(
            "### Destination Briefing\n\n"
            "Local knowledge retrieval was used for this search, but no destination briefing text was produced."
        )

    # Use multi-city or single-destination summary
    if is_multi_city:
        parts.append(_format_multi_city_summary(trip, trip_legs))
    else:
        parts.append(_format_trip_summary(trip, flights, hotels))

    flight_filters = _format_flight_filters(trip)
    if flight_filters:
        parts.append(flight_filters)

    if budget.get("budget_notes"):
        parts.append(f"### Budget Note\n\n> {budget['budget_notes']}")

    return {
        "messages": [{"role": "assistant", "content": "\n\n".join(parts)}],
        "current_step": WorkflowStep.AWAITING_REVIEW,
    }
