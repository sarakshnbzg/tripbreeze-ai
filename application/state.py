"""Graph state schema — defines the data flowing through the travel planning workflow."""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict


class TravelState(TypedDict, total=False):
    """Typed state passed between all nodes in the travel planning graph."""

    # Identity
    user_id: str

    # Runtime model selection
    llm_provider: str
    llm_model: str

    # Profile (from long-term memory)
    user_profile: dict[str, Any]

    # Structured form fields (passed directly from UI, skips LLM parsing)
    structured_fields: dict[str, Any]

    # Trip request (built from structured_fields + LLM-parsed preferences)
    trip_request: dict[str, Any]

    # Research results
    flight_options: list[dict]
    hotel_options: list[dict]
    destination_info: str
    rag_used: bool

    # Budget analysis
    budget: dict[str, Any]

    # Human-in-the-loop
    user_approved: bool
    user_feedback: str
    selected_flight: dict[str, Any]
    selected_hotel: dict[str, Any]

    # Final output
    final_itinerary: str

    # Conversation history (append-only via operator.add)
    messages: Annotated[list[dict], operator.add]

    # Control flow
    current_step: str
    error: str
