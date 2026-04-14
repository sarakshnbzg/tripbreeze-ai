"""Attractions research node — pulls candidate POIs for the destination.

Runs after the main research orchestrator so it has the destination fixed.
Results feed the finaliser, which sequences them into a day-by-day plan
grounded in the real candidate list (no invented POIs).
"""

from infrastructure.apis.serpapi_client import search_attractions
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def attractions_research(state: dict) -> dict:
    """LangGraph node: fetch attraction candidates for the destination."""
    trip_request = state.get("trip_request", {})
    destination = trip_request.get("destination", "")
    interests = trip_request.get("interests", []) or []

    if not destination:
        logger.info("attractions_research skipped — no destination in trip_request")
        return {"attraction_candidates": [], "current_step": "attractions_complete"}

    logger.info(
        "attractions_research started destination=%s interests=%s",
        destination,
        interests,
    )

    try:
        candidates = search_attractions(destination=destination, interests=interests)
    except Exception as exc:
        logger.exception("attractions_research failed: %s", exc)
        candidates = []

    logger.info("attractions_research finished candidates=%s", len(candidates))

    return {
        "attraction_candidates": candidates,
        "current_step": "attractions_complete",
    }
