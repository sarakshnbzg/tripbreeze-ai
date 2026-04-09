"""LangGraph workflow — wires domain nodes into the travel planning pipeline.

Dependency direction:  application → domain → infrastructure
This module only imports from the domain layer (nodes & agents).
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from application.state import TravelState
from domain.nodes.profile_loader import profile_loader
from domain.nodes.trip_intake import trip_intake
from domain.nodes.budget_aggregator import budget_aggregator
from domain.nodes.hitl_review import hitl_review
from domain.nodes.trip_finaliser import trip_finaliser
from domain.nodes.memory_updater import memory_updater
from domain.nodes.research_orchestrator import research_orchestrator
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── Routing ──

def _route_after_intake(state: dict) -> str:
    current_step = state.get("current_step")
    logger.info("Routing after intake: current_step=%s", current_step)
    if current_step == "intake_complete":
        return "continue"
    return "stop"


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
    graph.add_conditional_edges(
        "trip_intake",
        _route_after_intake,
        {"continue": "research", "stop": END},
    )

    # Dynamic ReAct-style research
    graph.add_edge("research", "aggregate_budget")

    # Budget → HITL review
    graph.add_edge("aggregate_budget", "review")

    # review always proceeds to finalise; the checkpointer's interrupt_before
    # pauses execution here so the user can review and approve first
    graph.add_edge("review", "finalise")

    # Finalise → memory → END
    graph.add_edge("finalise", "update_memory")
    graph.add_edge("update_memory", END)

    return graph


def compile_graph():
    """Compile the graph with a MemorySaver checkpointer.

    interrupt_before=["finalise"] makes the graph pause before the finalise
    node so the user can review options and approve.  Execution resumes when
    the caller updates state with user selections and calls graph.stream again.
    """
    logger.info("Compiling travel planning graph with MemorySaver checkpointer")
    checkpointer = MemorySaver()
    return build_graph().compile(checkpointer=checkpointer, interrupt_before=["finalise"])


def run_finalisation_streaming(graph, thread_id: str, state_updates: dict):
    """Resume the paused graph after user approval and stream the itinerary.

    Injects the user's flight/hotel selections and approval into the
    checkpointed state, then resumes execution through the finalise and
    update_memory nodes via the real graph edges.

    Yields str chunks for the UI to display, then yields the final state dict.

    Usage::

        for item in run_finalisation_streaming(graph, thread_id, updates):
            if isinstance(item, str):
                display(item)
            else:
                state = item  # final merged state
    """
    logger.info("Resuming graph for finalisation thread_id=%s", thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    graph.update_state(config, state_updates)
    for event in graph.stream(None, config):
        for node_name, node_output in event.items():
            if node_name == "finalise":
                itinerary = node_output.get("final_itinerary", "")
                if itinerary:
                    yield itinerary
    yield dict(graph.get_state(config).values)
