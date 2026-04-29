"""Support models and deterministic rendering helpers for the trip finaliser."""

import json
import re
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field, ValidationError

from application.state import TravelState
from infrastructure.apis.geocoding_client import geocode_address
from infrastructure.apis.serpapi_client import fetch_hotel_address
from infrastructure.apis.weather_client import fetch_weather_for_trip
from infrastructure.llms.model_factory import (
    create_chat_model,
    extract_token_usage,
    invoke_with_retry,
    stream_with_retry,
)
from domain.utils.dates import trip_duration_with_dates
from infrastructure.currency_utils import format_currency
from infrastructure.logging_utils import get_logger, log_event
from infrastructure.streaming import get_token_emitter

logger = get_logger(__name__)


class Source(BaseModel):
    """A knowledge-base source referenced in the itinerary."""

    document: str = Field(description="Name or identifier of the source document")
    snippet: str = Field(description="Relevant excerpt from the source document")


class Activity(BaseModel):
    """A single attraction or activity in a day plan."""

    name: str = Field(description="Name of the attraction as it appears in the candidate list.")
    time_of_day: str = Field(description="When to do this: morning, afternoon, or evening.")
    notes: str = Field(
        default="",
        description="One short sentence describing why this attraction fits the user's interests.",
    )
    category: str = Field(default="", description="Candidate category such as food, art, or history.")
    address: str = Field(default="", description="Street address or area for the attraction, if known.")
    latitude: float | None = Field(default=None, description="Latitude for map display, if known.")
    longitude: float | None = Field(default=None, description="Longitude for map display, if known.")
    maps_url: str = Field(default="", description="Google Maps URL for the attraction, if known.")
    destination: str = Field(default="", description="Destination city this attraction belongs to, if known.")
    is_mappable: bool = Field(
        default=True,
        description="Whether this activity should appear as a map pin. Set false for transfers, checkout, baggage storage, or flexible nearby placeholders.",
    )


class DayWeatherInfo(BaseModel):
    """Weather information for a single day."""

    temp_min: float = Field(description="Minimum temperature in Celsius")
    temp_max: float = Field(description="Maximum temperature in Celsius")
    condition: str = Field(description="Weather condition description")
    precipitation_chance: int = Field(description="Chance of precipitation (0-100%)")
    is_historical: bool = Field(default=False, description="True if based on historical data")


class DayPlan(BaseModel):
    """Plan for a single day of the trip."""

    day_number: int = Field(description="1-indexed day number.")
    date: str = Field(default="", description="ISO date (YYYY-MM-DD) for this day if known.")
    theme: str = Field(default="", description="Short theme for the day, e.g. 'Historic centre'.")
    activities: list[Activity] = Field(default_factory=list)
    weather: DayWeatherInfo | None = Field(default=None, description="Weather forecast for this day")


class Itinerary(BaseModel):
    """Structured final trip itinerary."""

    trip_overview: str = Field(description="Brief summary of the trip (destination, dates, travelers)")
    flight_details: str = Field(description="Details of the selected flight")
    hotel_details: str = Field(description="Details of the selected hotel")
    destination_highlights: str = Field(description="Key highlights, tips, and things to do at the destination")
    daily_plans: list[DayPlan] = Field(
        default_factory=list,
        description=(
            "Day-by-day plan. Each day should contain 2-5 activities chosen from the "
            "attraction candidate list. Leave empty only if no attractions were provided."
        ),
    )
    budget_breakdown: str = Field(description="Breakdown of costs in the trip currency")
    visa_entry_info: str = Field(description="Important visa, passport, and entry requirements")
    packing_tips: str = Field(description="Packing and preparation tips for the trip")
    sources: list[Source] = Field(
        default_factory=list,
        description="Knowledge-base documents referenced for destination information. Empty if none were used.",
    )


class LegDetails(BaseModel):
    """Details for a single leg of a multi-city trip."""

    leg_number: int = Field(description="1-indexed leg number")
    origin: str = Field(description="Departure city for this leg")
    destination: str = Field(description="Arrival city for this leg")
    departure_date: str = Field(description="Departure date in YYYY-MM-DD format")
    flight_summary: str = Field(description="Brief flight details (airline, times, duration)")
    hotel_summary: str = Field(default="", description="Brief hotel details (name, location). Empty for return legs.")
    nights: int = Field(default=0, description="Number of nights at this destination")


class MultiCityItinerary(BaseModel):
    """Structured final itinerary for multi-city trips."""

    trip_overview: str = Field(description="Brief summary of the multi-city trip (route, dates, travelers)")
    legs: list[LegDetails] = Field(description="Details for each leg of the trip")
    destination_highlights: str = Field(description="Key highlights and tips for all destinations visited")
    daily_plans: list[DayPlan] = Field(
        default_factory=list,
        description="Day-by-day plan spanning all legs chronologically.",
    )
    budget_breakdown: str = Field(description="Breakdown of costs across all legs in the trip currency")
    visa_entry_info: str = Field(description="Visa and entry requirements for all destinations")
    packing_tips: str = Field(description="Packing tips considering all destinations and weather")
    sources: list[Source] = Field(default_factory=list, description="Knowledge-base documents referenced.")


def _enrich_hotel_address(
    selected_hotel: dict,
    trip_request: dict,
    *,
    fetch_hotel_address_fn=fetch_hotel_address,
) -> None:
    """Resolve the selected hotel's street address via SerpAPI (in-place)."""
    if not selected_hotel or selected_hotel.get("address"):
        return
    property_token = selected_hotel.get("property_token")
    if not property_token:
        return
    address = fetch_hotel_address_fn(
        property_token=property_token,
        check_in=selected_hotel.get("check_in", trip_request.get("departure_date", "")),
        check_out=selected_hotel.get("check_out", trip_request.get("return_date", "")),
        adults=trip_request.get("num_travelers", 1),
        currency=selected_hotel.get("currency", trip_request.get("currency", "EUR")),
    )
    if address:
        selected_hotel["address"] = address
        logger.info("Resolved hotel address via property_token")


def _enrich_hotel_coordinates(
    selected_hotel: dict,
    destination_hint: str = "",
    *,
    geocode_fn=geocode_address,
) -> None:
    """Geocode the hotel's address into latitude/longitude (in-place)."""
    if not selected_hotel:
        return
    if selected_hotel.get("latitude") is not None and selected_hotel.get("longitude") is not None:
        return
    address = str(selected_hotel.get("address", "") or "").strip()
    if not address:
        return
    query = address
    hint = (destination_hint or "").strip()
    if hint and hint.lower() not in address.lower():
        query = f"{address}, {hint}"
    coords = geocode_fn(query)
    if coords:
        selected_hotel["latitude"], selected_hotel["longitude"] = coords
        logger.info("Geocoded hotel '%s' to (%.5f, %.5f)", selected_hotel.get("name", "?"), *coords)


def _is_generic_logistics_activity(name: str | None) -> bool:
    """Return True for generic transfer/check-out activities that should not be geocoded by name alone."""
    text = (name or "").strip().lower()
    if not text:
        return False

    generic_phrases = (
        "airport transfer",
        "transfer to airport",
        "airport",
        "check out",
        "checkout",
        "hotel checkout",
        "baggage storage",
        "luggage storage",
        "depart",
        "departure",
        "station transfer",
        "transfer to station",
    )
    return any(phrase in text for phrase in generic_phrases)


def _is_non_mappable_activity(name: str | None) -> bool:
    """Return True for activities that should stay in the itinerary but not appear on the map."""
    text = (name or "").strip().lower()
    if not text:
        return False
    if _is_generic_logistics_activity(text):
        return True

    placeholder_phrases = (
        "flexible activity",
        "nearby flexible activity",
        "flexible nearby activity",
    )
    return any(phrase in text for phrase in placeholder_phrases)


def _backfill_activity_coordinates(
    daily_plans: list,
    destination_by_date: dict[str, str] | None = None,
    *,
    geocode_fn=geocode_address,
) -> None:
    """Geocode any activity that has an address but no coordinates (in-place)."""
    if not daily_plans:
        return
    for day in daily_plans:
        day_hint = ""
        if destination_by_date and getattr(day, "date", None):
            day_hint = destination_by_date.get(day.date, "") or ""
        for activity in getattr(day, "activities", []) or []:
            if _is_non_mappable_activity(activity.name):
                activity.is_mappable = False
                continue
            if activity.latitude is not None and activity.longitude is not None:
                continue
            address = (activity.address or "").strip()
            if not address:
                continue
            fallback_hint = day_hint or (activity.destination or "")
            query_parts = [part for part in [activity.name, address, fallback_hint] if part]
            if not query_parts:
                continue
            coords = geocode_fn(", ".join(query_parts))
            if coords:
                activity.latitude, activity.longitude = coords
                activity.is_mappable = True


def _strip_generic_logistics_coordinates(daily_plans: list) -> None:
    """Remove map metadata from generic logistics activities.

    These items can be useful in the itinerary text, but they should not produce
    pins because model- or geocoder-supplied coordinates are often misleading.
    """
    if not daily_plans:
        return

    for day in daily_plans:
        for activity in getattr(day, "activities", []) or []:
            if not _is_non_mappable_activity(getattr(activity, "name", "")):
                activity.is_mappable = True
                continue
            activity.is_mappable = False
            activity.latitude = None
            activity.longitude = None
            activity.maps_url = ""


def _rescue_malformed_itinerary(raw: dict) -> dict:
    """Attempt to fix common malformed Itinerary output from LLMs."""
    fixed = dict(raw)
    daily_plans = fixed.get("daily_plans", [])

    valid_plans = []
    string_fragments = []
    for item in daily_plans:
        if isinstance(item, dict) and "day_number" in item:
            valid_plans.append(item)
        elif isinstance(item, str):
            string_fragments.append(item)

    fixed["daily_plans"] = valid_plans

    for fragment in string_fragments:
        for field in ("budget_breakdown", "visa_entry_info", "packing_tips"):
            if not fixed.get(field):
                for pattern in [f"{field}':", f'"{field}":', f"{field}:"]:
                    if pattern in fragment:
                        idx = fragment.find(pattern)
                        value = fragment[idx + len(pattern):].strip().strip("'\"")
                        if value:
                            fixed[field] = value
                            break

    if not fixed.get("budget_breakdown"):
        fixed["budget_breakdown"] = "Budget information unavailable."
    if not fixed.get("visa_entry_info"):
        fixed["visa_entry_info"] = "Please check visa requirements for your nationality."
    if not fixed.get("packing_tips"):
        fixed["packing_tips"] = "Pack according to weather and planned activities."

    return fixed


def _run_finaliser_react_loop(
    *,
    state: TravelState,
    prompt: str,
    final_tool_model,
    final_tool_name: str,
    initial_user_message: str,
    retrieve_knowledge_tool=None,
    token_node_name: str,
    completion_log_name: str,
    create_chat_model_fn=create_chat_model,
    extract_token_usage_fn=extract_token_usage,
    invoke_with_retry_fn=invoke_with_retry,
) -> tuple[dict, list[dict], list[dict], dict]:
    model = state.get("llm_model")
    llm = create_chat_model_fn(
        state.get("llm_provider"),
        model,
        temperature=float(state.get("llm_temperature", 0.5)),
    )
    tools = [final_tool_model]
    tools_by_name = {}
    if retrieve_knowledge_tool is not None:
        tools.insert(0, retrieve_knowledge_tool)
        tools_by_name["retrieve_knowledge"] = retrieve_knowledge_tool

    llm_with_tools = llm.bind_tools(tools)

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=initial_user_message),
    ]

    token_usage: list[dict] = []
    final_result: dict = {}
    diagnostics = {
        "iterations": 0,
        "termination_reason": "unknown",
        "final_tool_emitted": False,
        "tool_calls": [],
        "unknown_tool_calls": [],
        "tool_errors": [],
    }

    for iteration in range(4):
        diagnostics["iterations"] = iteration + 1
        response = invoke_with_retry_fn(llm_with_tools, messages)
        messages.append(response)
        token_usage.append(extract_token_usage_fn(response, model=model, node=token_node_name))

        if not getattr(response, "tool_calls", None):
            logger.info("%s completed without further tool calls", completion_log_name)
            diagnostics["termination_reason"] = "no_tool_calls"
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            diagnostics["tool_calls"].append(tool_name)
            logger.info("%s received tool call %s", completion_log_name, tool_name)
            log_event(
                logger,
                "workflow.tool_called",
                workflow_node=token_node_name,
                tool_name=tool_name,
                iteration=iteration + 1,
            )

            if tool_name == final_tool_name:
                final_result = tool_call.get("args", {})
                diagnostics["final_tool_emitted"] = True
                diagnostics["termination_reason"] = "final_tool"
                messages.append(ToolMessage(
                    content=f"{final_tool_name} received.",
                    tool_call_id=tool_call["id"],
                ))
                logger.info("%s received final itinerary", completion_log_name)
                break

            if tool_name not in tools_by_name:
                logger.warning("%s received unknown tool call: %s", completion_log_name, tool_name)
                diagnostics["unknown_tool_calls"].append(tool_name)
                messages.append(ToolMessage(
                    content=f"Error: unknown tool '{tool_name}'.",
                    tool_call_id=tool_call["id"],
                ))
                continue

            try:
                tool_started_at = datetime.now()
                tool_result = tools_by_name[tool_name].invoke(tool_call.get("args", {}))
                log_event(
                    logger,
                    "workflow.tool_completed",
                    workflow_node=token_node_name,
                    tool_name=tool_name,
                    latency_ms=round((datetime.now() - tool_started_at).total_seconds() * 1000, 2),
                )
            except Exception as exc:
                logger.exception("%s tool %s failed", completion_log_name, tool_name)
                diagnostics["tool_errors"].append({"tool": tool_name, "error": str(exc)})
                log_event(
                    logger,
                    "workflow.tool_failed",
                    workflow_node=token_node_name,
                    tool_name=tool_name,
                    error_type=type(exc).__name__,
                )
                tool_result = json.dumps({"error": str(exc)})
            messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))

        if final_result:
            break
    else:
        logger.warning("%s exhausted all %s iterations without a final result", completion_log_name, 4)
        diagnostics["termination_reason"] = "max_iterations"

    if diagnostics["termination_reason"] in ("", "unknown"):
        diagnostics["termination_reason"] = "completed_without_final_tool"

    return final_result, token_usage, messages, diagnostics


def _parse_structured_itinerary(
    *,
    final_result: dict,
    model_class,
    rescue_log_name: str,
):
    try:
        return model_class(**final_result)
    except ValidationError as exc:
        logger.warning("%s validation failed, attempting rescue: %s", rescue_log_name, exc)
        rescued = _rescue_malformed_itinerary(final_result)
        try:
            return model_class(**rescued)
        except ValidationError:
            logger.exception("%s rescue failed", rescue_log_name)
            return None


def _enrich_single_city_weather(
    itinerary: Itinerary,
    destination: str,
    *,
    fetch_weather_for_trip_fn=fetch_weather_for_trip,
) -> None:
    day_dates = [day.date for day in itinerary.daily_plans if day.date]
    if not destination or not day_dates:
        return

    weather_data = fetch_weather_for_trip_fn(destination, day_dates)
    for day in itinerary.daily_plans:
        if day.date and day.date in weather_data:
            w = weather_data[day.date]
            day.weather = DayWeatherInfo(
                temp_min=w.temp_min,
                temp_max=w.temp_max,
                condition=w.condition,
                precipitation_chance=w.precipitation_chance,
                is_historical=w.is_historical,
            )
    logger.info("Enriched %d daily plans with weather data", len(weather_data))


def _enrich_multi_city_weather(
    itinerary: MultiCityItinerary,
    trip_legs: list[dict],
    *,
    fetch_weather_for_trip_fn=fetch_weather_for_trip,
) -> None:
    date_to_destination = _weather_destination_by_date(trip_legs)
    weather_requests: dict[str, list[str]] = {}
    for day in itinerary.daily_plans:
        if day.date and day.date in date_to_destination:
            destination = date_to_destination[day.date]
            weather_requests.setdefault(destination, []).append(day.date)

    for destination, dates in weather_requests.items():
        weather_data = fetch_weather_for_trip_fn(destination, sorted(set(dates)))
        for day in itinerary.daily_plans:
            if day.date and day.date in weather_data and date_to_destination.get(day.date) == destination:
                w = weather_data[day.date]
                day.weather = DayWeatherInfo(
                    temp_min=w.temp_min,
                    temp_max=w.temp_max,
                    condition=w.condition,
                    precipitation_chance=w.precipitation_chance,
                    is_historical=w.is_historical,
                )


def _chunk_text(chunk: Any) -> str:
    """Extract plain text from a LangChain streaming chunk."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


def _render_markdown_with_live_stream(
    state: TravelState,
    itinerary,
    fallback_markdown: str,
    *,
    render_prompt: str,
    create_chat_model_fn=create_chat_model,
    stream_with_retry_fn=stream_with_retry,
    get_token_emitter_fn=get_token_emitter,
) -> str:
    """Render the user-facing markdown with true model streaming when an emitter is active."""
    token_emitter = get_token_emitter_fn()
    if token_emitter is None:
        return fallback_markdown

    model = state.get("llm_model")
    llm = create_chat_model_fn(
        state.get("llm_provider"),
        model,
        temperature=0,
    )
    prompt = render_prompt.format(
        itinerary_json=json.dumps(itinerary.model_dump(), indent=2, ensure_ascii=True),
    )

    rendered_parts: list[str] = []
    try:
        for chunk in stream_with_retry_fn(llm, prompt):
            text = _chunk_text(chunk)
            if not text:
                continue
            rendered_parts.append(text)
            token_emitter(text)
    except Exception:
        logger.exception("Live markdown rendering failed; falling back to deterministic renderer")
        return fallback_markdown

    rendered_markdown = "".join(rendered_parts).strip()
    return rendered_markdown or fallback_markdown


def _normalise_place_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _candidate_lookup(candidates: list[dict]) -> dict[str, list[dict]]:
    lookup: dict[str, list[dict]] = {}
    for candidate in candidates:
        key = _normalise_place_key(str(candidate.get("name", "")))
        if key:
            lookup.setdefault(key, []).append(candidate)
    return lookup


def _apply_activity_location_metadata(
    daily_plans: list[DayPlan],
    candidates: list[dict],
    *,
    destination_by_date: dict[str, str] | None = None,
) -> None:
    """Backfill map fields from the canonical attraction candidates by name."""
    if not daily_plans or not candidates:
        return

    lookup = _candidate_lookup(candidates)
    for day in daily_plans:
        day_destination = ""
        if destination_by_date and day.date:
            day_destination = str(destination_by_date.get(day.date, "")).strip().lower()
        for activity in day.activities:
            key = _normalise_place_key(activity.name)
            matches = lookup.get(key, [])
            if not matches:
                continue
            candidate = matches[0]
            if day_destination:
                for match in matches:
                    candidate_destination = str(match.get("destination", "")).strip().lower()
                    if candidate_destination == day_destination:
                        candidate = match
                        break

            if not activity.category:
                activity.category = str(candidate.get("category", "") or "")
            if not activity.address:
                activity.address = str(candidate.get("address", "") or "")
            if activity.latitude is None:
                activity.latitude = candidate.get("latitude")
            if activity.longitude is None:
                activity.longitude = candidate.get("longitude")
            if not activity.maps_url:
                activity.maps_url = str(candidate.get("maps_url", "") or "")
            if not activity.destination:
                activity.destination = str(candidate.get("destination", "") or "")


def _looks_like_structured_markdown(body: str) -> bool:
    stripped = body.lstrip()
    return stripped.startswith(("-", "*", "|", "1.", "###", "####"))


def _sentence_bullets(body: str) -> str:
    """Convert plain prose into a compact markdown bullet list."""
    text = re.sub(r"\s+", " ", body).strip()
    if not text:
        return body

    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if part.strip()
    ]
    if len(parts) <= 1:
        return f"- {text}"
    return "\n".join(f"- {part}" for part in parts)


def _render_section_body(title: str, body: str) -> str:
    """Improve scannability for dense final-itinerary sections."""
    if title not in {"🛫 Flight Details", "🏨 Hotel Details"}:
        return body
    if _looks_like_structured_markdown(body):
        return body
    return _sentence_bullets(body)


def _strip_source_suffix(text: str) -> str:
    return re.sub(r"\s*\(Source: [^)]+\)\s*", "", text).strip()


def _parse_multi_city_destination_info(destination_info: str) -> tuple[str, str]:
    """Split multi-city briefing markdown into highlights vs entry requirements."""
    if not destination_info:
        return "", ""

    highlights: list[str] = []
    entries: list[str] = []
    sections = [
        section.strip()
        for section in re.split(r"\n\s*---\s*\n", destination_info)
        if "#### 🌍 Overview" in section or "#### 🛂 Entry Requirements" in section
    ]

    for section in sections:
        header_match = re.search(r"^###\s+(.+?)\n", section, flags=re.MULTILINE)
        if not header_match:
            continue
        destination = header_match.group(1).strip()
        body = section[header_match.end():].strip()
        overview_match = re.search(
            r"####\s+🌍 Overview\n(.*?)(?=^####\s+|\Z)",
            body,
            flags=re.MULTILINE | re.DOTALL,
        )
        entry_match = re.search(
            r"####\s+🛂 Entry Requirements\n(.*?)(?=^####\s+|\Z)",
            body,
            flags=re.MULTILINE | re.DOTALL,
        )

        if overview_match:
            overview = _strip_source_suffix(overview_match.group(1).strip())
            highlights.append(f"- **{destination}:** {overview}")
        if entry_match:
            entry = entry_match.group(1).strip()
            if entry.startswith("### "):
                lines = entry.splitlines()
                heading = _strip_source_suffix(lines[0].lstrip("# ").strip())
                bullet_lines = [_strip_source_suffix(line.strip()) for line in lines[1:] if line.strip()]
                entries.append(f"**{destination} — {heading}**")
                entries.extend(bullet_lines)
            else:
                entries.append(f"- **{destination}:** {_strip_source_suffix(entry)}")

    return "\n".join(highlights).strip(), "\n".join(entries).strip()


def _multi_city_flight_summary(flight: dict, currency: str) -> str:
    """Build a readable per-leg flight summary without relying on one optional field."""
    if not flight:
        return "Flight details unavailable"

    summary = str(flight.get("outbound_summary", "")).strip()
    if summary:
        return summary

    airline = str(flight.get("airline", "")).strip()
    departure_time = str(flight.get("departure_time", "")).strip()
    arrival_time = str(flight.get("arrival_time", "")).strip()
    duration = str(flight.get("duration", "")).strip()
    stops = flight.get("stops")
    total_price = flight.get("total_price", flight.get("price"))

    parts = []
    route_bits = []
    if airline:
        parts.append(airline)
    if departure_time or arrival_time:
        route_bits.append(f"{departure_time or '?'} → {arrival_time or '?'}")
    if duration:
        route_bits.append(duration)
    if isinstance(stops, int):
        route_bits.append("Direct" if stops == 0 else f"{stops} stop" if stops == 1 else f"{stops} stops")
    if route_bits:
        parts.append(" · ".join(route_bits))
    if isinstance(total_price, (int, float)) and total_price > 0:
        parts.append(f"{currency} {total_price:g} total")

    return " — ".join(parts) if parts else "Flight details unavailable"


def _format_multi_city_budget(budget: dict, currency: str) -> str:
    """Render the multi-city budget dict as readable markdown."""
    if not budget:
        return "Budget details unavailable."

    lines = [
        f"- Flights: {format_currency(budget.get('flight_cost', 0), currency)}",
        f"- Hotels: {format_currency(budget.get('hotel_cost', 0), currency)}",
        f"- Estimated daily expenses: {format_currency(budget.get('estimated_daily_expenses', 0), currency)}",
        f"- Total estimated trip cost: {format_currency(budget.get('total_estimated', 0), currency)}",
    ]
    if budget.get("budget_notes"):
        lines.append(f"- Note: {budget['budget_notes']}")

    per_leg = budget.get("per_leg_breakdown") or []
    if per_leg:
        lines.extend(["", "**Per leg**"])
        for leg in per_leg:
            route = f"{leg.get('origin', '?')} → {leg.get('destination', '?')}"
            nights = leg.get("nights", 0)
            lines.append(
                f"- {route} ({nights} night{'s' if nights != 1 else ''}): "
                f"flight {format_currency(leg.get('flight_cost', 0), currency)}, "
                f"hotel {format_currency(leg.get('hotel_cost', 0), currency)}, "
                f"daily {format_currency(leg.get('daily_expenses', 0), currency)}, "
                f"total {format_currency(leg.get('leg_total', 0), currency)}"
            )

    return "\n".join(lines)


def _multi_city_packing_tips(trip_request: dict, trip_legs: list[dict]) -> str:
    destinations = [leg.get("destination", "?") for leg in trip_legs if leg.get("nights", 0) > 0]
    destinations_text = ", ".join(destinations) if destinations else "your destinations"
    departure_date = str(trip_request.get("departure_date", "")).strip()
    month_hint = ""
    if departure_date:
        try:
            month_hint = datetime.fromisoformat(departure_date).strftime("%B")
        except ValueError:
            month_hint = ""

    tips = [f"- Pack light layers and comfortable walking shoes for {destinations_text}."]
    if month_hint:
        tips.append(f"- For {month_hint} travel, bring a light jacket and sun protection for long sightseeing days.")
    tips.append("- Keep passports, booking confirmations, and intercity travel details easy to access between legs.")
    return "\n".join(tips)


def _build_multi_city_daily_plans(trip_legs: list[dict]) -> list[DayPlan]:
    """Create a simple chronological day plan for multi-city trips."""
    plans: list[DayPlan] = []
    day_number = 1

    for leg_index, leg in enumerate(trip_legs):
        destination = str(leg.get("destination", "")).strip()
        origin = str(leg.get("origin", "")).strip()
        departure_date = str(leg.get("departure_date", "")).strip()
        nights = int(leg.get("nights", 0) or 0)

        if not departure_date:
            continue

        if nights <= 0:
            if leg_index == len(trip_legs) - 1 and origin and destination:
                plans.append(
                    DayPlan(
                        day_number=day_number,
                        date=departure_date,
                        theme=f"Departure day — depart {origin} for {destination}",
                        activities=[],
                    )
                )
                day_number += 1
            continue

        try:
            start_date = datetime.fromisoformat(departure_date)
        except ValueError:
            continue

        for offset in range(nights):
            date_str = (start_date.date() + timedelta(days=offset)).isoformat()

            if offset == 0:
                theme = f"Arrive in {destination} from {origin}".strip()
            elif offset == nights - 1:
                theme = f"Final full day in {destination}"
            else:
                theme = f"Explore {destination}"

            plans.append(
                DayPlan(
                    day_number=day_number,
                    date=date_str,
                    theme=theme,
                    activities=[],
                )
            )
            day_number += 1

    return plans


def _weather_destination_by_date(trip_legs: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for leg_index, leg in enumerate(trip_legs):
        destination = str(leg.get("destination", "")).strip()
        origin = str(leg.get("origin", "")).strip()
        departure_date = str(leg.get("departure_date", "")).strip()
        nights = int(leg.get("nights", 0) or 0)
        if not departure_date:
            continue
        if nights <= 0:
            if leg_index == len(trip_legs) - 1 and origin:
                mapping[departure_date] = origin
            continue
        try:
            start_date = datetime.fromisoformat(departure_date).date()
        except ValueError:
            continue
        for offset in range(nights):
            mapping[(start_date + timedelta(days=offset)).isoformat()] = destination
    return mapping


def _extract_single_city_destination_sections(destination_info: str) -> tuple[str, str]:
    if not destination_info:
        return "", ""

    overview_match = re.search(
        r"####\s+🌍 Overview\n(.*?)(?=^####\s+|\Z)",
        destination_info,
        flags=re.MULTILINE | re.DOTALL,
    )
    entry_match = re.search(
        r"####\s+🛂 Entry Requirements\n(.*?)(?=^####\s+|\Z)",
        destination_info,
        flags=re.MULTILINE | re.DOTALL,
    )
    overview = _strip_source_suffix(overview_match.group(1).strip()) if overview_match else ""
    entry = entry_match.group(1).strip() if entry_match else ""
    return overview, _strip_source_suffix(entry)


def _build_single_city_fallback_itinerary(state: TravelState, fallback_reason: str) -> Itinerary:
    trip_request = state.get("trip_request", {})
    selected_flight = state.get("selected_flight", {})
    selected_hotel = state.get("selected_hotel", {})
    attraction_candidates = state.get("attraction_candidates", []) or []
    destination_info = state.get("destination_info", "") or ""
    budget = state.get("budget", {}) or {}
    destination = str(trip_request.get("destination", "") or "your destination").strip()
    origin = str(trip_request.get("origin", "") or "your origin").strip()
    currency = trip_request.get("currency", "EUR")
    num_travelers = trip_request.get("num_travelers", 1)
    interests = ", ".join(trip_request.get("interests", []) or [])
    overview, visa_info = _extract_single_city_destination_sections(destination_info)
    _num_days, day_dates = trip_duration_with_dates(trip_request)
    return_date = str(trip_request.get("return_date", "") or "").strip()
    departure_date = str(trip_request.get("departure_date", "") or "").strip()
    if return_date and return_date != departure_date:
        day_dates = day_dates + [return_date]
    daily_plans = [
        DayPlan(
            day_number=idx + 1,
            date=date_value,
            theme=(
                f"Arrival and first impressions in {destination}"
                if idx == 0
                else f"Departure and wrap-up in {destination}"
                if idx == len(day_dates) - 1 and return_date
                else f"Explore {destination}"
            ),
            activities=[],
        )
        for idx, date_value in enumerate(day_dates)
    ]

    trip_overview = (
        f"{origin} to {destination} for {len(day_dates)} day(s), "
        f"for {num_travelers} traveler{'s' if num_travelers != 1 else ''}."
    )
    flight_details = _sentence_bullets(
        _multi_city_flight_summary(selected_flight, currency)
        if selected_flight
        else "Flight details were not fully generated, so please refer to the selected option in the review step."
    )
    hotel_name = selected_hotel.get("name") if selected_hotel else ""
    hotel_bits = []
    if hotel_name:
        hotel_bits.append(str(hotel_name))
    if selected_hotel.get("rating"):
        hotel_bits.append(f"Rated {selected_hotel['rating']}")
    if selected_hotel.get("address"):
        hotel_bits.append(str(selected_hotel["address"]))
    hotel_details = _sentence_bullets(
        ". ".join(hotel_bits)
        if hotel_bits
        else "Hotel details were not fully generated, so please refer to the selected option in the review step."
    )
    destination_highlights = overview or f"{destination} trip details were preserved, but the model did not finish the polished highlights section."
    if interests:
        destination_highlights += f" Planned interests: {interests}."
    if attraction_candidates:
        destination_highlights += f" {len(attraction_candidates)} attraction candidate(s) are available for manual planning."

    budget_breakdown = _sentence_bullets(
        f"Estimated total trip cost: {format_currency(budget.get('total_estimated', 0), currency)}."
        if budget
        else "Budget summary unavailable."
    )
    packing_tips = (
        f"- Pack for the season in {destination} and keep travel documents handy.\n"
        f"- Fallback itinerary generated because the model ended with: {fallback_reason or 'an incomplete response'}."
    )
    return Itinerary(
        trip_overview=trip_overview,
        flight_details=flight_details,
        hotel_details=hotel_details,
        destination_highlights=destination_highlights,
        daily_plans=daily_plans,
        budget_breakdown=budget_breakdown,
        visa_entry_info=visa_info or "Please verify current visa and passport requirements for your nationality before departure.",
        packing_tips=packing_tips,
        sources=[Source(document=source, snippet="Referenced earlier in the trip-planning flow.") for source in state.get("rag_sources", []) or []],
    )


def _build_multi_city_fallback_itinerary(state: TravelState, fallback_reason: str) -> MultiCityItinerary:
    trip_request = state.get("trip_request", {})
    trip_legs = state.get("trip_legs", []) or []
    selected_flights = state.get("selected_flights", []) or []
    selected_hotels = state.get("selected_hotels", []) or []
    destination_info = state.get("destination_info", "") or ""
    budget = state.get("budget", {}) or {}
    currency = trip_request.get("currency", "EUR")
    destinations = [str(leg.get("destination", "")).strip() for leg in trip_legs if int(leg.get("nights", 0) or 0) > 0]
    legs = []
    for idx, leg in enumerate(trip_legs, start=1):
        flight = selected_flights[idx - 1] if idx - 1 < len(selected_flights) else {}
        hotel = selected_hotels[idx - 1] if idx - 1 < len(selected_hotels) else {}
        legs.append(
            LegDetails(
                leg_number=idx,
                origin=str(leg.get("origin", "") or "?"),
                destination=str(leg.get("destination", "") or "?"),
                departure_date=str(leg.get("departure_date", "") or ""),
                flight_summary=_multi_city_flight_summary(flight, currency),
                hotel_summary=str(hotel.get("name", "") or ""),
                nights=int(leg.get("nights", 0) or 0),
            )
        )

    highlights, visa_info = _parse_multi_city_destination_info(destination_info)
    route = " → ".join(
        [str(trip_request.get("origin", "") or "").strip(), *[d for d in destinations if d]]
    ).strip(" →")
    if trip_request.get("return_date") and trip_legs:
        route += f" → {trip_legs[-1].get('destination', '')}".rstrip()
    if not route:
        route = "Multi-city trip"

    return MultiCityItinerary(
        trip_overview=f"{route} for {trip_request.get('num_travelers', 1)} traveler(s).",
        legs=legs,
        destination_highlights=highlights or "Trip structure is available, but the model did not finish the polished highlights section.",
        daily_plans=_build_multi_city_daily_plans(trip_legs),
        budget_breakdown=_format_multi_city_budget(budget, currency),
        visa_entry_info=visa_info or "Please verify entry requirements for each destination before departure.",
        packing_tips=_multi_city_packing_tips(trip_request, trip_legs) + (
            f"\n- Fallback itinerary generated because the model ended with: {fallback_reason or 'an incomplete response'}."
        ),
        sources=[Source(document=source, snippet="Referenced earlier in the trip-planning flow.") for source in state.get("rag_sources", []) or []],
    )


def _render_daily_plans(daily_plans: list[DayPlan]) -> str:
    if not daily_plans:
        return "_Attraction suggestions unavailable — see Destination Highlights for ideas._"
    day_chunks = []
    for day in daily_plans:
        heading = f"##### Day {day.day_number}"
        if day.theme:
            heading += f" — {day.theme}"
        if day.date:
            heading += f"  _({day.date})_"
        lines = [heading]
        if day.weather:
            w = day.weather
            weather_line = f"🌡️ {w.temp_min:.0f}–{w.temp_max:.0f}°C, {w.condition}"
            if w.precipitation_chance > 0:
                weather_line += f", {w.precipitation_chance}% chance of rain"
            if w.is_historical:
                weather_line += " _(typical for this time of year)_"
            lines.append(weather_line)
        for act in day.activities:
            time_of_day = (act.time_of_day or "").strip().lower() or "anytime"
            note = f": {act.notes}" if act.notes else ""
            activity_text = f"- **{time_of_day}** — {act.name}{note}"
            if act.maps_url:
                activity_text += f" ([Open in Google Maps]({act.maps_url}))"
            lines.append(activity_text)
        day_chunks.append("\n".join(lines))
    return "\n\n".join(day_chunks)


def render_itinerary_markdown(itinerary: Itinerary) -> str:
    """Render a structured Itinerary as a user-facing markdown string."""
    sections = [
        ("✈️ Trip Overview", itinerary.trip_overview),
        ("🛫 Flight Details", itinerary.flight_details),
        ("🏨 Hotel Details", itinerary.hotel_details),
        ("🌍 Destination Highlights", itinerary.destination_highlights),
        ("🗓️ Day-by-Day Plan", _render_daily_plans(itinerary.daily_plans)),
        ("💰 Budget Breakdown", itinerary.budget_breakdown),
        ("🛂 Visa & Entry Information", itinerary.visa_entry_info),
        ("🎒 Packing & Preparation Tips", itinerary.packing_tips),
    ]
    parts = [f"#### {title}\n{_render_section_body(title, body)}" for title, body in sections]

    if itinerary.sources:
        source_lines = []
        for src in itinerary.sources:
            source_lines.append(f"- **{src.document}**: {src.snippet}")
        parts.append("#### 📚 Sources (from Knowledge Base)\n" + "\n".join(source_lines))

    return "\n\n".join(parts)


def render_multi_city_itinerary_markdown(itinerary: MultiCityItinerary) -> str:
    """Render a structured MultiCityItinerary as a user-facing markdown string."""
    parts = [f"#### ✈️ Trip Overview\n{itinerary.trip_overview}"]

    parts.append("#### 🗺️ Trip Legs")
    for leg in itinerary.legs:
        leg_header = f"**Leg {leg.leg_number}: {leg.origin} → {leg.destination}**"
        if leg.nights > 0:
            leg_header += f" ({leg.nights} night{'s' if leg.nights != 1 else ''})"
        parts.append(leg_header)
        parts.append(f"- 📅 {leg.departure_date}")
        parts.append(f"- ✈️ {leg.flight_summary}")
        if leg.hotel_summary:
            parts.append(f"- 🏨 {leg.hotel_summary}")

    sections = [
        ("🌍 Destination Highlights", itinerary.destination_highlights),
        ("🗓️ Day-by-Day Plan", _render_daily_plans(itinerary.daily_plans)),
        ("💰 Budget Breakdown", itinerary.budget_breakdown),
        ("🛂 Visa & Entry Information", itinerary.visa_entry_info),
        ("🎒 Packing & Preparation Tips", itinerary.packing_tips),
    ]
    for title, body in sections:
        parts.append(f"#### {title}\n{body}")

    if itinerary.sources:
        source_lines = [f"- **{src.document}**: {src.snippet}" for src in itinerary.sources]
        parts.append("#### 📚 Sources (from Knowledge Base)\n" + "\n".join(source_lines))

    return "\n\n".join(parts)
