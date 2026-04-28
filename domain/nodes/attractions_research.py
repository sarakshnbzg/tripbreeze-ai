"""Attractions research node — pulls candidate POIs for the destination.

Runs after the main research orchestrator so it has the destination fixed.
Results feed the finaliser, which sequences them into a day-by-day plan
grounded in the real candidate list (no invented POIs).
"""

from application.workflow_types import WorkflowStep
from infrastructure.apis.serpapi_client import search_attractions
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def attractions_research(state: dict) -> dict:
    """LangGraph node: fetch attraction candidates for the destination."""
    trip_request = state.get("trip_request", {})
    interests = trip_request.get("interests", []) or []
    trip_legs = state.get("trip_legs", []) or []

    destinations: list[str] = []
    for leg in trip_legs:
        destination = str(leg.get("destination", "")).strip()
        if destination and destination not in destinations and int(leg.get("nights", 0) or 0) > 0:
            destinations.append(destination)

    if not destinations:
        destination = str(trip_request.get("destination", "")).strip()
        if destination:
            destinations.append(destination)

    if not destinations:
        logger.info("attractions_research skipped — no destinations available")
        return {"attraction_candidates": [], "current_step": WorkflowStep.ATTRACTIONS_COMPLETE}

    logger.info(
        "attractions_research started destinations=%s interests=%s",
        destinations,
        interests,
    )

    candidates = []
    try:
        seen_names: set[str] = set()
        for destination in destinations:
            for candidate in search_attractions(destination=destination, interests=interests):
                name = str(candidate.get("name", "")).strip().lower()
                if name and name in seen_names:
                    continue
                if name:
                    seen_names.add(name)
                enriched_candidate = dict(candidate)
                enriched_candidate.setdefault("destination", destination)
                candidates.append(enriched_candidate)
    except Exception as exc:
        logger.exception("attractions_research failed: %s", exc)
        candidates = []

    logger.info("attractions_research finished candidates=%s", len(candidates))

    return {
        "attraction_candidates": candidates,
        "current_step": WorkflowStep.ATTRACTIONS_COMPLETE,
    }
