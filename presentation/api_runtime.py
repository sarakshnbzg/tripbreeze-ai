"""Shared runtime objects for the FastAPI backend."""

import threading
from concurrent.futures import ThreadPoolExecutor

from application.graph import compile_graph
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

executor = ThreadPoolExecutor(max_workers=4)

NODE_LABELS = {
    "load_profile": "Loading your traveler profile...",
    "trip_intake": "Understanding your trip request...",
    "research": "Researching flights, hotels, and destination info...",
    "aggregate_budget": "Calculating budget breakdown...",
    "review": "Preparing your trip summary...",
    "feedback_router": "Updating the workflow based on your decision...",
    "attractions": "Finding attractions for your itinerary...",
    "finalise": "Finalising your itinerary...",
    "update_memory": "Saving your travel preferences...",
}

_graph = None
_graph_lock = threading.Lock()


def get_graph():
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                _graph = compile_graph()
    return _graph
