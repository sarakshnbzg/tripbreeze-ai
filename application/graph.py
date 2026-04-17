"""LangGraph workflow — wires domain nodes into the travel planning pipeline.

Dependency direction:  application → domain → infrastructure
This module only imports from the domain layer (nodes & agents).
"""

import re

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from application.state import TravelState
from infrastructure.persistence.checkpointer import get_checkpointer
from domain.nodes.attractions_research import attractions_research
from domain.nodes.profile_loader import profile_loader
from domain.nodes.trip_intake import trip_intake
from domain.nodes.budget_aggregator import budget_aggregator
from domain.nodes.hitl_review import hitl_review
from domain.nodes.review_router import build_revision_query, review_router
from domain.nodes.trip_finaliser import trip_finaliser
from domain.nodes.memory_updater import memory_updater
from domain.nodes.research_orchestrator import research_orchestrator
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _iter_text_chunks(text: str):
    """Yield markdown text in word-sized chunks for a smoother UI reveal."""
    for chunk in re.split(r"(\s+)", text):
        if chunk:
            yield chunk


# ── Routing ──

def _route_after_intake(state: dict) -> str:
    current_step = state.get("current_step")
    logger.info("Routing after intake: current_step=%s", current_step)
    if current_step == "intake_complete":
        return "continue"
    return "stop"


def _route_after_review_router(state: dict) -> str:
    feedback_type = str(state.get("feedback_type") or "").strip().lower()
    logger.info(
        "Routing after review router: feedback_type=%s user_approved=%s",
        feedback_type,
        bool(state.get("user_approved")),
    )
    if feedback_type == "revise_plan":
        return "revise"
    if feedback_type == "cancel":
        return "stop"
    return "approve"


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
    graph.add_node("feedback_router", review_router)
    graph.add_node("attractions", attractions_research)
    graph.add_node("finalise", trip_finaliser)
    graph.add_node("update_memory", memory_updater)

    # Edges: linear start
    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "trip_intake")
    graph.add_conditional_edges(
        "trip_intake",
        _route_after_intake,
        {"continue": "research", "stop": END},
    )

    # Dynamic ReAct-style research
    graph.add_edge("research", "aggregate_budget")

    # Budget → HITL review
    graph.add_edge("aggregate_budget", "review")

    graph.add_edge("review", "feedback_router")
    graph.add_conditional_edges(
        "feedback_router",
        _route_after_review_router,
        {
            "approve": "attractions",
            "revise": "trip_intake",
            "stop": END,
        },
    )

    graph.add_edge("attractions", "finalise")

    # Finalise → memory → END
    graph.add_edge("finalise", "update_memory")
    graph.add_edge("update_memory", END)

    return graph


def compile_graph():
    """Compile the graph with a persistent checkpointer.

    Uses PostgresSaver (Neon) when DATABASE_URL is configured so HITL review
    state survives Streamlit server restarts; falls back to MemorySaver
    otherwise.
    """
    logger.info("Compiling travel planning graph")
    return build_graph().compile(checkpointer=get_checkpointer())


def run_finalisation_streaming(graph, thread_id: str, state_updates: dict):
    """Resume the graph after review and yield final itinerary chunks."""
    logger.info("Resuming graph for finalisation thread_id=%s", thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    for event in graph.stream(Command(resume=state_updates), config):
        for node_name, node_output in event.items():
            if node_name != "finalise" or not isinstance(node_output, dict):
                continue
            itinerary_markdown = str(node_output.get("final_itinerary") or "")
            if itinerary_markdown:
                yield from _iter_text_chunks(itinerary_markdown)

    yield dict(graph.get_state(config).values)
