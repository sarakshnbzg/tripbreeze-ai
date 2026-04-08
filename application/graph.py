"""LangGraph workflow — wires domain nodes into the travel planning pipeline.

Dependency direction:  application → domain → infrastructure
This module only imports from the domain layer (nodes & agents).
"""

from datetime import datetime

from langgraph.graph import StateGraph, START, END

from application.state import TravelState
from domain.agents.flight_agent import search_flights
from domain.agents.hotel_agent import search_hotels
from domain.nodes.profile_loader import profile_loader
from domain.nodes.trip_intake import trip_intake
from domain.nodes.budget_aggregator import budget_aggregator
from domain.nodes.trip_finaliser import trip_finaliser
from domain.nodes.memory_updater import memory_updater
from domain.nodes.research_orchestrator import destination_research
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── HITL review node ──


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
    parts.append(
        "### Next Step\n\n"
        "Review the options below, choose your preferred flight and hotel, "
        "then approve to generate the final itinerary."
    )

    return {
        "messages": [{"role": "assistant", "content": "\n\n".join(parts)}],
        "current_step": "awaiting_review",
    }


# ── Routing ──

def _route_after_review(state: dict) -> str:
    logger.info("Routing after review: user_approved=%s", state.get("user_approved", False))
    if state.get("user_approved"):
        return "finalise"
    return "awaiting_input"


# ── Graph construction ──

def build_graph() -> StateGraph:
    """Construct the LangGraph travel-planning workflow."""
    logger.info("Building travel planning graph")
    graph = StateGraph(TravelState)

    # Nodes
    graph.add_node("load_profile", profile_loader)
    graph.add_node("trip_intake", trip_intake)
    graph.add_node("flight_search", search_flights)
    graph.add_node("hotel_search", search_hotels)
    graph.add_node("destination_research", destination_research)
    graph.add_node("aggregate_budget", budget_aggregator)
    graph.add_node("review", hitl_review)
    graph.add_node("finalise", trip_finaliser)
    graph.add_node("update_memory", memory_updater)

    # Edges: linear start
    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "trip_intake")

    # Progressive research nodes
    graph.add_edge("trip_intake", "destination_research")
    graph.add_edge("destination_research", "flight_search")
    graph.add_edge("flight_search", "hotel_search")
    graph.add_edge("hotel_search", "aggregate_budget")

    # Budget → HITL review
    graph.add_edge("aggregate_budget", "review")

    # Conditional: approve → finalise, else → END (wait for more input)
    graph.add_conditional_edges(
        "review",
        _route_after_review,
        {"finalise": "finalise", "awaiting_input": END},
    )

    # Finalise → memory → END
    graph.add_edge("finalise", "update_memory")
    graph.add_edge("update_memory", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    logger.info("Compiling travel planning graph")
    return build_graph().compile()


_APPEND_KEYS = {"messages", "token_usage"}


def _merge_node_output(state: dict, output: dict) -> None:
    """Merge a node's output into state, appending list-valued keys instead of overwriting."""
    for key, value in output.items():
        if key in _APPEND_KEYS and isinstance(value, list):
            state.setdefault(key, [])
            state[key].extend(value)
        else:
            state[key] = value


def run_finalisation(state: dict) -> dict:
    """Run the finalise and memory-update nodes outside the graph.

    Called by the presentation layer after the user approves their
    selections, keeping domain imports out of the UI module.
    """
    logger.info("Running finalisation for user_id=%s", state.get("user_id"))
    _merge_node_output(state, trip_finaliser(state))
    _merge_node_output(state, memory_updater(state))
    return state
