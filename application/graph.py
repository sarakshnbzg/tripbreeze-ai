"""LangGraph workflow — wires domain nodes into the travel planning pipeline.

Dependency direction:  application → domain → infrastructure
This module only imports from the domain layer (nodes & agents).
"""

from langgraph.graph import StateGraph, START, END

from application.state import TravelState
from domain.nodes.profile_loader import profile_loader
from domain.nodes.trip_intake import trip_intake
from domain.nodes.budget_aggregator import budget_aggregator
from domain.nodes.trip_finaliser import trip_finaliser
from domain.nodes.memory_updater import memory_updater
from domain.nodes.research_orchestrator import research_orchestrator
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── HITL review node ──


def _format_trip_summary(trip: dict, flights: list[dict], hotels: list[dict]) -> str:
    route = f"{trip.get('origin', '?')} -> {trip.get('destination', '?')}"
    dates = f"{trip.get('departure_date', '?')} to {trip.get('return_date', '?')}"
    travelers = trip.get("num_travelers", 1)
    class_name = str(trip.get("travel_class", "ECONOMY")).replace("_", " ").title()

    return "\n".join(
        [
            "**Trip Summary**",
            f"- Route: {route}",
            f"- Dates: {dates}",
            f"- Travelers: {travelers}",
            f"- Cabin class: {class_name}",
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
        heading = "**Destination Briefing**"
        if rag_used:
            source_list = ", ".join(rag_sources) if rag_sources else "local knowledge base"
            heading += f"\n**Sources:** {source_list}"
        parts.append(f"{heading}\n{dest_info}")
    elif rag_used:
        parts.append(
            "**From RAG**\n"
            "Local knowledge retrieval was used for this search, but no destination briefing text was produced."
        )

    parts.append(_format_trip_summary(trip, flights, hotels))
    if budget.get("budget_notes"):
        parts.append(f"**Budget Note**\n{budget['budget_notes']}")
    parts.append("**Next Step**\nPlease select your preferred flight and hotel below.")

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
    graph.add_node("research", research_orchestrator)
    graph.add_node("aggregate_budget", budget_aggregator)
    graph.add_node("review", hitl_review)
    graph.add_node("finalise", trip_finaliser)
    graph.add_node("update_memory", memory_updater)

    # Edges: linear start
    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "trip_intake")

    # Dynamic research orchestration
    graph.add_edge("trip_intake", "research")
    graph.add_edge("research", "aggregate_budget")

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
