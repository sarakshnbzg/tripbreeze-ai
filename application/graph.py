"""LangGraph workflow — wires domain nodes into the travel planning pipeline.

Dependency direction:  application → domain → infrastructure
This module only imports from the domain layer (nodes & agents).
"""

from langgraph.graph import StateGraph, START, END

from application.state import TravelState
from domain.nodes.profile_loader import profile_loader
from domain.nodes.trip_intake import trip_intake
from domain.nodes.budget_aggregator import budget_aggregator
from domain.nodes.hitl_review import hitl_review
from domain.nodes.trip_finaliser import trip_finaliser, trip_finaliser_stream
from domain.nodes.memory_updater import memory_updater
from domain.nodes.research_orchestrator import research_orchestrator
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── Routing ──

def _route_after_review(state: dict) -> str:
    logger.info("Routing after review: user_approved=%s", state.get("user_approved", False))
    if state.get("user_approved"):
        return "finalise"
    return "awaiting_input"


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


def run_finalisation_streaming(state: dict):
    """Generator: yield markdown chunks, then run memory updater.

    Yields str chunks for the UI to display progressively. After the
    stream finishes, runs memory_updater and yields the final state dict.

    Usage::

        for item in run_finalisation_streaming(state):
            if isinstance(item, str):
                display(item)
            else:
                state = item  # final merged state
    """
    logger.info("Running streaming finalisation for user_id=%s", state.get("user_id"))
    for item in trip_finaliser_stream(state):
        if isinstance(item, str):
            yield item
        else:
            _merge_node_output(state, item)

    _merge_node_output(state, memory_updater(state))
    yield state
