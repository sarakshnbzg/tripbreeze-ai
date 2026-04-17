"""Review router node — decides what to do after the user reviews options."""

from langgraph.types import interrupt

from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


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
    is_revision = feedback_type == "revise_plan"

    logger.info(
        "review_router received feedback_type=%s user_approved=%s",
        feedback_type,
        bool(decision.get("user_approved", state.get("user_approved"))),
    )

    if not is_revision:
        return {
            **decision,
            "current_step": "approval_received",
            "feedback_type": feedback_type or "rewrite_itinerary",
            "user_approved": bool(decision.get("user_approved", state.get("user_approved", True))),
        }

    return {
        **decision,
        "user_approved": False,
        "current_step": "revising_plan",
        "structured_fields": {},
        "free_text_query": build_revision_query(state),
        "selected_flight": {},
        "selected_hotel": {},
        "selected_transport": {},
        "selected_flights": [],
        "selected_hotels": [],
        "flight_options": [],
        "hotel_options": [],
        "transport_options": [],
        "flight_options_by_leg": [],
        "hotel_options_by_leg": [],
        "budget": {},
        "destination_info": "",
        "rag_used": False,
        "rag_sources": [],
        "rag_trace": [],
        "attraction_candidates": [],
        "final_itinerary": "",
        "itinerary_data": {},
        "finaliser_metadata": {},
    }
