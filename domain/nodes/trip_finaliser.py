"""Trip Finaliser node — generates the polished itinerary document."""

import json

from pydantic import BaseModel, Field

from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


# ── Structured output models ──────────────────────────────────────────


class Source(BaseModel):
    """A knowledge-base source referenced in the itinerary."""

    document: str = Field(description="Name or identifier of the source document")
    snippet: str = Field(description="Relevant excerpt from the source document")


class Itinerary(BaseModel):
    """Structured final trip itinerary."""

    trip_overview: str = Field(description="Brief summary of the trip (destination, dates, travelers)")
    flight_details: str = Field(description="Details of the selected flight")
    hotel_details: str = Field(description="Details of the selected hotel")
    destination_highlights: str = Field(description="Key highlights, tips, and things to do at the destination")
    budget_breakdown: str = Field(description="Breakdown of costs in the trip currency")
    visa_entry_info: str = Field(description="Important visa, passport, and entry requirements")
    packing_tips: str = Field(description="Packing and preparation tips for the trip")
    sources: list[Source] = Field(
        default_factory=list,
        description="Knowledge-base documents referenced for destination information. Empty if none were used.",
    )


# ── Prompt ────────────────────────────────────────────────────────────

FINALISER_PROMPT = """You are a travel planning assistant. Create a well-organized final trip itinerary.
All prices should be shown in {currency}.

Trip Details:
{trip_request}

Selected Flight:
{selected_flight}

Selected Hotel:
{selected_hotel}

Destination Information:
{destination_info}

Knowledge Base Sources Used:
{rag_sources}

Budget Summary:
{budget}

User Feedback (if any): {feedback}

Fill in every field of the requested schema. For the sources list, include an entry for each
knowledge-base document that was referenced in the destination information. Each source must
have the document name and a short relevant snippet from that document. Leave sources empty
only if no knowledge-base sources were used."""


# ── Helpers ───────────────────────────────────────────────────────────


def render_itinerary_markdown(itinerary: Itinerary) -> str:
    """Render a structured Itinerary as a user-facing markdown string."""
    sections = [
        ("✈️ Trip Overview", itinerary.trip_overview),
        ("🛫 Flight Details", itinerary.flight_details),
        ("🏨 Hotel Details", itinerary.hotel_details),
        ("🌍 Destination Highlights", itinerary.destination_highlights),
        ("💰 Budget Breakdown", itinerary.budget_breakdown),
        ("🛂 Visa & Entry Information", itinerary.visa_entry_info),
        ("🎒 Packing & Preparation Tips", itinerary.packing_tips),
    ]
    parts = [f"## {title}\n{body}" for title, body in sections]

    if itinerary.sources:
        source_lines = []
        for src in itinerary.sources:
            source_lines.append(f"- **{src.document}**: {src.snippet}")
        parts.append("## 📚 Sources\n" + "\n".join(source_lines))

    return "\n\n".join(parts)


# ── Node ──────────────────────────────────────────────────────────────


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
    structured_llm = llm.with_structured_output(Itinerary, include_raw=True)
    prompt = FINALISER_PROMPT.format(
        currency=state.get("trip_request", {}).get("currency", "EUR"),
        trip_request=json.dumps(state.get("trip_request", {}), indent=2),
        selected_flight=json.dumps(selected_flight, indent=2) or "No flight selected",
        selected_hotel=json.dumps(selected_hotel, indent=2) or "No hotel selected",
        destination_info=state.get("destination_info", "") or "No destination info available",
        rag_sources=", ".join(state.get("rag_sources", [])) or "None",
        budget=json.dumps(state.get("budget", {}), indent=2) or "No budget info",
        feedback=state.get("user_feedback", "") or "None",
    )
    result = invoke_with_retry(structured_llm, prompt)
    itinerary: Itinerary = result["parsed"]
    logger.info("Finaliser completed itinerary generation")

    usage = extract_token_usage(result["raw"], model=model, node="trip_finaliser")

    markdown = render_itinerary_markdown(itinerary)

    return {
        "final_itinerary": markdown,
        "itinerary_data": itinerary.model_dump(),
        "token_usage": [usage],
        "messages": [{"role": "assistant", "content": markdown}],
        "current_step": "finalised",
    }
