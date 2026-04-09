"""HITL Review node — formats research results for human inspection."""

from datetime import datetime

from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _markdown_table_value(value: object) -> str:
    """Keep dynamic values safe inside Markdown table cells."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _trip_nights(trip: dict) -> int | str:
    """Return trip nights from return/check-out dates when available."""
    departure_date = trip.get("departure_date", "")
    end_date = trip.get("return_date", "") or trip.get("check_out_date", "")
    if not departure_date or not end_date:
        return "?"
    try:
        d1 = datetime.strptime(departure_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return "?"
    return max((d2 - d1).days, 1)


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
    nights = _trip_nights(trip)

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


def hitl_review(state: dict) -> dict:
    """Prepare the review summary for the user to approve or adjust."""
    flights = state.get("flight_options", [])
    hotels = state.get("hotel_options", [])
    budget = state.get("budget", {})
    dest_info = state.get("destination_info", "")
    rag_used = state.get("rag_used", False)
    rag_sources = state.get("rag_sources", [])
    trip = state.get("trip_request", {})
    logger.info(
        "Preparing HITL review with %s flights, %s hotels, budget_present=%s, destination_info_present=%s",
        len(flights),
        len(hotels),
        bool(budget),
        bool(dest_info),
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

    parts.append(_format_trip_summary(trip, flights, hotels))
    if budget.get("budget_notes"):
        parts.append(f"### Budget Note\n\n> {budget['budget_notes']}")

    return {
        "messages": [{"role": "assistant", "content": "\n\n".join(parts)}],
        "current_step": "awaiting_review",
    }
