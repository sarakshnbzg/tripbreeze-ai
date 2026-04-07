"""Research orchestrator — lets the LLM dynamically choose which research tools to call."""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from domain.agents.flight_agent import search_flights
from domain.agents.hotel_agent import search_hotels
from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger
from infrastructure.rag.vectorstore import retrieve

logger = get_logger(__name__)

RESEARCH_PROMPT = """You are the research orchestrator for a travel planning app.
You can call tools to research flights, hotels, and destination information.

Use a ReAct-style workflow:
- decide what information is needed
- call tools only when useful
- you may call the same tool more than once if needed
- retrieval is optional, not mandatory
- after tool use, call `SubmitResearchResult` exactly once with your final structured output

Available tools:
- `search_flights`: search live flights when enough trip details are available
- `search_hotels`: search live hotels when enough trip details are available
- `retrieve_knowledge`: search the local travel knowledge base for destination, visa, transport, safety, and budget information
- `SubmitResearchResult`: submit the final structured research summary and destination briefing

Do not call tools that are impossible because required inputs are missing.
If the knowledge base is thin, say that clearly instead of inventing facts.
Only describe hotel star filtering as a user-requested criterion when `trip_request.hotel_stars_user_specified` is true.

When writing the destination_briefing, cite the source of each piece of information
inline using the source labels returned by `retrieve_knowledge`.
Use the format "(Source: <label>)" at the end of each relevant sentence or paragraph.

Prefer filling the structured destination fields over destination_briefing.
Use the structured fields only when grounded in retrieved knowledge, and keep each
field concise:
- destination_overview: why the destination is relevant for this trip
- entry_requirements: visa, passport, or entry notes when available
- transport_tips: airport transfer or local transport tips when available
- safety_notes: safety, local norms, or practical cautions when available
- budget_tips: cost-saving or budget expectations when available
"""

DESTINATION_INFO_SECTIONS = (
    ("destination_overview", "Overview"),
    ("entry_requirements", "Entry Requirements"),
    ("transport_tips", "Transport"),
    ("safety_notes", "Safety"),
    ("budget_tips", "Budget Tips"),
)


class SubmitResearchResult(BaseModel):
    """Structured final output for the research step."""

    summary: str = Field(description="Short grounded summary of the research results for the user.")
    destination_overview: str = Field(
        default="",
        description="Concise overview of the destination, with inline source citations.",
    )
    entry_requirements: str = Field(
        default="",
        description="Visa, passport, or entry requirement notes, with inline source citations.",
    )
    transport_tips: str = Field(
        default="",
        description="Airport transfer or local transport notes, with inline source citations.",
    )
    safety_notes: str = Field(
        default="",
        description="Safety, local norms, or practical caution notes, with inline source citations.",
    )
    budget_tips: str = Field(
        default="",
        description="Budget expectations or cost-saving tips, with inline source citations.",
    )
    destination_briefing: str = Field(
        default="",
        description=(
            "Legacy fallback destination briefing text. Prefer the structured "
            "destination fields when possible. Leave empty if no destination briefing is available."
        ),
    )


def _query_is_visa_related(query: str) -> bool:
    lowered = query.lower()
    keywords = ("visa", "entry", "passport", "immigration", "etias", "esta")
    return any(keyword in lowered for keyword in keywords)


def _enrich_retrieval_query(query: str, trip_request: dict[str, Any], user_profile: dict[str, Any]) -> str:
    """Inject saved profile context into visa-related knowledge queries."""
    if not _query_is_visa_related(query):
        return query

    destination = trip_request.get("destination", "")
    passport_country = user_profile.get("passport_country", "")

    additions = []
    if passport_country:
        additions.append(f"for travelers with a passport from {passport_country}")
    if destination:
        additions.append(f"visiting {destination}")

    if not additions:
        return query

    return f"{query.strip()} {' '.join(additions)}".strip()


def _build_research_summary(results: dict[str, Any], final_response: str) -> str:
    text = final_response.strip()

    # Strip the destination briefing from the chat summary — it is
    # displayed separately in the review-actions panel.
    marker = "Destination briefing:"
    if marker in text:
        text = text.split(marker, 1)[0].strip()

    if text:
        return text

    parts = ["Research complete."]
    if results.get("flight_options") is not None:
        parts.append(f"Flights found: {len(results.get('flight_options', []))}.")
    if results.get("hotel_options") is not None:
        parts.append(f"Hotels found: {len(results.get('hotel_options', []))}.")
    if results.get("destination_info"):
        parts.append("Destination briefing prepared.")
    return " ".join(parts)


def _format_destination_info(final_result: dict[str, Any]) -> str:
    """Format structured destination fields into a stable user-facing briefing."""
    sections = []
    for field_name, heading in DESTINATION_INFO_SECTIONS:
        content = str(final_result.get(field_name, "")).strip()
        if content:
            sections.append(f"**{heading}**\n{content}")

    if sections:
        return "\n\n".join(sections)

    # Backward-compatible fallback for older model/tool outputs.
    return str(final_result.get("destination_briefing", "")).strip()


def research_orchestrator(state: dict) -> dict:
    """LangGraph node: let the LLM choose which research tools to run."""
    trip_request = state.get("trip_request", {})
    user_profile = state.get("user_profile", {})
    logger.info(
        "Research orchestrator started destination=%s departure=%s return=%s",
        trip_request.get("destination"),
        trip_request.get("departure_date"),
        trip_request.get("return_date"),
    )

    collected: dict[str, Any] = {
        "flight_options": state.get("flight_options"),
        "hotel_options": state.get("hotel_options"),
        "destination_info": state.get("destination_info", ""),
        "rag_used": False,
        "rag_sources": [],
    }

    tool_state = {
        "trip_request": trip_request,
        "user_profile": user_profile,
        "messages": [],
    }

    @tool("search_flights")
    def search_flights_tool() -> str:
        """Search live flight options for the current trip request."""
        logger.info("Research orchestrator invoking search_flights tool")
        result = search_flights(tool_state)
        collected["flight_options"] = result.get("flight_options", [])
        return json.dumps(
            {
                "flight_count": len(collected["flight_options"] or []),
                "status": result.get("messages", [{}])[-1].get("content", "Flight search complete."),
            }
        )

    @tool("search_hotels")
    def search_hotels_tool() -> str:
        """Search live hotel options for the current trip request."""
        logger.info("Research orchestrator invoking search_hotels tool")
        result = search_hotels(tool_state)
        collected["hotel_options"] = result.get("hotel_options", [])
        return json.dumps(
            {
                "hotel_count": len(collected["hotel_options"] or []),
                "status": result.get("messages", [{}])[-1].get("content", "Hotel search complete."),
            }
        )

    @tool("retrieve_knowledge")
    def retrieve_knowledge_tool(query: str) -> str:
        """Search the local travel knowledge base for destination, visa, transport, safety, and budget information."""
        effective_query = _enrich_retrieval_query(query, trip_request, user_profile)
        logger.info(
            "Research orchestrator invoking retrieve_knowledge query=%s effective_query=%s",
            query,
            effective_query,
        )
        collected["rag_used"] = True
        results = retrieve(effective_query, provider=state.get("llm_provider"))
        # Track unique sources across all retrieval calls
        for r in results:
            if r["source"] not in collected["rag_sources"]:
                collected["rag_sources"].append(r["source"])
        return json.dumps({
            "query": effective_query,
            "chunks": [
                {"content": r["content"], "source": r["source"]} for r in results
            ],
        })

    final_result: dict[str, Any] = {}
    token_usage: list[dict] = []

    model = state.get("llm_model")
    llm = create_chat_model(
        state.get("llm_provider"),
        model,
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(
        [search_flights_tool, search_hotels_tool, retrieve_knowledge_tool, SubmitResearchResult]
    )

    messages = [
        SystemMessage(content=RESEARCH_PROMPT),
        HumanMessage(
            content=(
                "Research this trip request and decide which tools to use.\n\n"
                f"Trip request: {json.dumps(trip_request)}\n"
                f"User profile: {json.dumps(user_profile)}\n\n"
                "When you are done, call `SubmitResearchResult` exactly once. "
                "If you used `retrieve_knowledge`, include a concise destination briefing in `destination_briefing`."
            )
        ),
    ]

    final_response = ""
    tools_by_name = {
        "search_flights": search_flights_tool,
        "search_hotels": search_hotels_tool,
        "retrieve_knowledge": retrieve_knowledge_tool,
    }

    for _ in range(6):
        response = invoke_with_retry(llm_with_tools, messages)
        messages.append(response)
        token_usage.append(extract_token_usage(response, model=model, node="research_orchestrator"))

        if not getattr(response, "tool_calls", None):
            final_response = response.content if isinstance(response.content, str) else ""
            logger.info("Research orchestrator completed without further tool calls")
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            logger.info("Research orchestrator received tool call %s", tool_name)
            if tool_name == "SubmitResearchResult":
                final_result = tool_call.get("args", {})
                final_response = final_result.get("summary", "")
                logger.info("Research orchestrator received final structured result")
                break
            tool_result = tools_by_name[tool_name].invoke(tool_call.get("args", {}))
            messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))
        if final_result:
            break

    formatted_destination_info = _format_destination_info(final_result)
    if formatted_destination_info:
        collected["destination_info"] = formatted_destination_info

    summary = final_result.get("summary") or _build_research_summary(collected, final_response)
    logger.info(
        "Research orchestrator finished flights=%s hotels=%s destination_info_present=%s",
        len(collected.get("flight_options") or []),
        len(collected.get("hotel_options") or []),
        bool(collected.get("destination_info")),
    )

    return {
        "flight_options": collected.get("flight_options") or [],
        "hotel_options": collected.get("hotel_options") or [],
        "destination_info": collected.get("destination_info") or "",
        "rag_used": bool(collected.get("rag_used")),
        "rag_sources": collected.get("rag_sources") or [],
        "token_usage": token_usage,
        "messages": [{"role": "assistant", "content": summary}],
        "current_step": "research_complete",
    }
