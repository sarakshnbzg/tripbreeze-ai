"""Trip Finaliser node — generates the polished itinerary document."""

import json

from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

FINALISER_PROMPT = """You are a travel planning assistant. Create a beautiful, well-organized final trip itinerary
based on the user's selections. Format it nicely with sections and emojis. All prices should be shown in {currency}.

Trip Details:
{trip_request}

Selected Flight:
{selected_flight}

Selected Hotel:
{selected_hotel}

Destination Information:
{destination_info}

Budget Summary:
{budget}

User Feedback (if any): {feedback}

Create a comprehensive but concise trip plan that includes:
1. Trip overview
2. Flight details (the user's chosen flight)
3. Hotel details (the user's chosen hotel)
4. Destination highlights and tips
5. Budget breakdown in the trip currency ({currency})
6. Important visa/entry information
7. Packing and preparation tips

Make it feel like a professional travel itinerary document."""


def trip_finaliser(state: dict) -> dict:
    """LangGraph node: generate the final trip itinerary."""
    selected_flight = state.get("selected_flight", {})
    selected_hotel = state.get("selected_hotel", {})
    logger.info(
        "Finaliser started with selected_flight=%s, selected_hotel=%s, destination_info_present=%s, feedback_present=%s",
        bool(selected_flight),
        bool(selected_hotel),
        bool(state.get("destination_info")),
        bool(state.get("user_feedback")),
    )
    model = state.get("llm_model")
    llm = create_chat_model(
        state.get("llm_provider"),
        model,
        temperature=0.5,
    )
    response = invoke_with_retry(
        llm,
        FINALISER_PROMPT.format(
            currency=state.get("trip_request", {}).get("currency", "EUR"),
            trip_request=json.dumps(state.get("trip_request", {}), indent=2),
            selected_flight=json.dumps(selected_flight, indent=2) or "No flight selected",
            selected_hotel=json.dumps(selected_hotel, indent=2) or "No hotel selected",
            destination_info=state.get("destination_info", "") or "No destination info available",
            budget=json.dumps(state.get("budget", {}), indent=2) or "No budget info",
            feedback=state.get("user_feedback", "") or "None",
        )
    )
    logger.info("Finaliser completed itinerary generation")

    usage = extract_token_usage(response, model=model, node="trip_finaliser")

    return {
        "final_itinerary": response.content,
        "token_usage": [usage],
        "messages": [{"role": "assistant", "content": response.content}],
        "current_step": "finalised",
    }
