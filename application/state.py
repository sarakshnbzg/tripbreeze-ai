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
    llm_temperature: float

    # Profile (from long-term memory)
    user_profile: dict[str, Any]

    # Free-text trip query (natural language input from the user)
    free_text_query: str

    # Structured form fields (passed directly from UI, skips LLM parsing)
    structured_fields: dict[str, Any]
    revision_baseline: dict[str, Any]

    # Trip request (built from structured_fields + LLM-parsed preferences)
    trip_request: dict[str, Any]

    # Research results
    flight_options: list[dict]
    hotel_options: list[dict]
    destination_info: str
    rag_used: bool
    rag_sources: list[str]
    rag_trace: list[dict[str, Any]]
    attraction_candidates: list[dict]

    # Budget analysis
    budget: dict[str, Any]

    # Human-in-the-loop
    user_approved: bool
    user_feedback: str
    feedback_type: str
    selected_flight: dict[str, Any]
    selected_hotel: dict[str, Any]
    # Multi-city support
    trip_legs: list[dict[str, Any]]  # [{origin, destination, departure_date, nights, needs_hotel}, ...]
    flight_options_by_leg: list[list[dict]]  # Per-leg flight options
    hotel_options_by_leg: list[list[dict]]  # Per-leg hotel options
    selected_flights: list[dict[str, Any]]  # User selection per leg
    selected_hotels: list[dict[str, Any]]  # User selection per leg (empty dict if no hotel)

    # Final output
    final_itinerary: str
    itinerary_data: dict[str, Any]
    finaliser_metadata: dict[str, Any]

    # Conversation history (append-only via operator.add)
    messages: Annotated[list[dict], operator.add]

    # Token usage tracking (append-only via operator.add)
    token_usage: Annotated[list[dict], operator.add]

    # Control flow
    current_step: str
    error: str
