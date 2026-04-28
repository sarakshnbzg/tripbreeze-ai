"""Review router node — decides what to do after the user reviews options."""

import re
from datetime import date, timedelta

from langgraph.types import interrupt

from application.state import REVISION_RESET
from application.workflow_types import FeedbackType, WorkflowStep
from infrastructure.logging_utils import get_logger, log_event

logger = get_logger(__name__)

_NIGHTS_PATTERN = re.compile(r"\b(\d+)\s*nights?\b", re.IGNORECASE)


def build_revision_query(state: dict) -> str:
    """Turn review-time feedback into a fresh intake prompt."""
    trip = state.get("trip_request", {}) or {}
    trip_legs = state.get("trip_legs", []) or []
    feedback = (state.get("user_feedback") or "").strip()

    base_lines = [
        "Revise this travel plan based on the user's feedback.",
        "",
        f"Current origin: {trip.get('origin') or 'Unknown'}",
        f"Current destination: {trip.get('destination') or 'Unknown'}",
        f"Departure date: {trip.get('departure_date') or 'Unknown'}",
    ]

    if trip.get("return_date"):
        base_lines.append(f"Return date: {trip.get('return_date')}")
    if trip.get("check_out_date"):
        base_lines.append(f"Check-out date: {trip.get('check_out_date')}")
    if trip.get("num_travelers"):
        base_lines.append(f"Travelers: {trip.get('num_travelers')}")
    if trip.get("budget_limit"):
        base_lines.append(
            f"Budget limit: {trip.get('budget_limit')} {trip.get('currency') or 'EUR'}"
        )
    if trip.get("travel_class"):
        base_lines.append(f"Travel class: {trip.get('travel_class')}")
    if trip.get("preferences"):
        base_lines.append(f"Current preferences: {trip.get('preferences')}")

    if trip_legs:
        base_lines.append("Current multi-city legs:")
        for leg in trip_legs:
            base_lines.append(
                f"- {leg.get('origin', '?')} to {leg.get('destination', '?')} on "
                f"{leg.get('departure_date', '?')} for {leg.get('nights', 0)} night(s)"
            )

    base_lines.extend(
        [
            "",
            "User feedback to apply:",
            feedback or "No additional feedback provided.",
            "",
            "Return the updated trip details only.",
        ]
    )
    return "\n".join(base_lines)


def _extract_requested_nights(feedback: str) -> int | None:
    match = _NIGHTS_PATTERN.search(feedback or "")
    if not match:
        return None
    try:
        nights = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return nights if nights > 0 else None


def _build_revision_baseline(state: dict, feedback: str = "") -> dict:
    trip = dict(state.get("trip_request", {}) or {})
    feedback = str(feedback or state.get("user_feedback") or "")
    trip_legs = state.get("trip_legs", []) or []

    # Single-destination duration changes can be patched deterministically.
    requested_nights = _extract_requested_nights(feedback)
    departure_date = str(trip.get("departure_date") or "").strip()
    if requested_nights and departure_date and not trip_legs:
        try:
            updated_end_date = (
                date.fromisoformat(departure_date) + timedelta(days=requested_nights)
            ).isoformat()
        except ValueError:
            updated_end_date = ""

        if updated_end_date:
            if trip.get("return_date"):
                trip["return_date"] = updated_end_date
                trip["check_out_date"] = ""
            else:
                trip["check_out_date"] = updated_end_date
                trip["return_date"] = ""

    return trip


def review_router(state: dict) -> dict:
    """Pause for the user's review decision, then prepare the next graph hop."""
    decision = interrupt(
        {
            "type": "review_decision",
            "question": "Review the current options and choose whether to approve or revise the plan.",
        }
    )
    decision = decision if isinstance(decision, dict) else {}
    feedback_type = str(decision.get("feedback_type") or state.get("feedback_type") or "").strip().lower()
    user_feedback = str(decision.get("user_feedback") or state.get("user_feedback") or "").strip()
    is_revision = feedback_type == FeedbackType.REVISE_PLAN

    logger.info(
        "review_router received feedback_type=%s user_approved=%s",
        feedback_type,
        bool(decision.get("user_approved", state.get("user_approved"))),
    )
    log_event(
        logger,
        "workflow.review_decision_received",
        feedback_type=feedback_type or FeedbackType.REWRITE_ITINERARY,
        user_approved=bool(decision.get("user_approved", state.get("user_approved"))),
    )

    if not is_revision:
        return {
            **decision,
            "current_step": WorkflowStep.APPROVAL_RECEIVED,
            "feedback_type": feedback_type or FeedbackType.REWRITE_ITINERARY,
            "user_feedback": user_feedback,
            "user_approved": bool(decision.get("user_approved", state.get("user_approved", True))),
        }

    return {
        **decision,
        **REVISION_RESET,
        "user_approved": False,
        "current_step": WorkflowStep.REVISING_PLAN,
        "user_feedback": user_feedback,
        "revision_baseline": _build_revision_baseline(state, user_feedback),
        "free_text_query": user_feedback,
    }
