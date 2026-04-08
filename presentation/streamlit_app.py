"""Streamlit UI for TripBreeze AI.

Dependency direction: presentation -> application -> domain -> infrastructure
This module only imports from the application and infrastructure layers.
"""

import streamlit as st

from datetime import date, timedelta
from typing import Any

from config import (
    AIRLINES,
    CITIES,
    COUNTRIES,
    CURRENCIES,
    DEFAULT_CURRENCY,
    DESTINATIONS,
    HOTEL_STARS,
    TRAVEL_CLASSES,
)
from application.graph import compile_graph as _compile_graph, run_finalisation
from infrastructure.apis.serpapi_client import search_return_flights
from infrastructure.currency_utils import format_currency, normalise_currency
from infrastructure.logging_utils import get_logger
from infrastructure.llms.model_factory import (
    get_available_models,
    get_provider_status,
    normalise_llm_selection,
)
from infrastructure.persistence.memory_store import load_profile, save_profile, list_profiles


@st.cache_resource
def _get_graph():
    return _compile_graph()

logger = get_logger(__name__)

st.set_page_config(page_title="TripBreeze AI", page_icon="✈️", layout="wide")


SESSION_DEFAULTS = {
    "messages": [],
    "graph_state": None,
    "token_usage_history": [],
    "awaiting_review": False,
    "trip_complete": False,
    "user_id": "default_user",
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
}

MODEL_LABELS = {
    "gpt-4o-mini": "OpenAI GPT-4o mini",
    "gpt-4.1-mini": "OpenAI GPT-4.1 mini",
    "gpt-4.1-nano": "OpenAI GPT-4.1 nano",
    "gpt-3.5-turbo": "OpenAI GPT-3.5 Turbo",
    "gemini-2.5-flash": "Google Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Google Gemini 2.5 Flash-Lite",
}


@st.cache_data(show_spinner=False, ttl=3600)
def _get_return_flight_options(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    departure_token: str,
    adults: int,
    travel_class: str,
    currency: str,
    return_time_window: tuple[int, int] | None,
) -> list[dict]:
    return search_return_flights(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        departure_token=departure_token,
        adults=adults,
        travel_class=travel_class,
        currency=currency,
        return_time_window=return_time_window,
    )


def _normalise_time_window(raw_window: object) -> tuple[int, int] | None:
    if not isinstance(raw_window, list) or len(raw_window) != 2:
        return None
    try:
        start = int(raw_window[0])
        end = int(raw_window[1])
    except (TypeError, ValueError):
        return None
    if 0 <= start <= end <= 23:
        return start, end
    return None


def _combine_round_trip_flight(outbound: dict, return_flight: dict) -> dict:
    """Store the user's outbound and return choices as one itinerary object."""
    total_price = return_flight.get("total_price", outbound.get("total_price", outbound.get("price", 0)))
    adults = outbound.get("adults", 1)
    price = round(total_price / adults, 2) if adults > 1 else total_price
    return {
        **outbound,
        "return_summary": return_flight.get("return_summary", outbound.get("return_summary", "")),
        "return_details_available": True,
        "selected_return": return_flight,
        "total_price": total_price,
        "price": price,
        "currency": return_flight.get("currency", outbound.get("currency")),
    }


def _format_stops(stops: int) -> str:
    if stops == 0:
        return "Direct"
    return f"{stops} stop" if stops == 1 else f"{stops} stops"


def _option_total_price(option: dict) -> float:
    return float(option.get("total_price", option.get("price", 0)) or 0)


def _format_option_price(option: dict, currency: str) -> str:
    total_price = _option_total_price(option)
    price_label = format_currency(total_price, currency)
    if option.get("adults", 1) > 1:
        price_label += f" total ({format_currency(option.get('price', 0), currency)}/person)"
    return price_label


def _duration_to_minutes(option: dict) -> int:
    raw_duration = str(option.get("duration", ""))
    hours = 0
    minutes = 0
    for part in raw_duration.split():
        if part.endswith("h"):
            try:
                hours = int(part[:-1])
            except ValueError:
                pass
        elif part.endswith("m"):
            try:
                minutes = int(part[:-1])
            except ValueError:
                pass
    return hours * 60 + minutes


def _flight_badges(options: list[dict], option: dict) -> list[str]:
    badges = []
    prices = [_option_total_price(item) for item in options if _option_total_price(item) > 0]
    durations = [_duration_to_minutes(item) for item in options if _duration_to_minutes(item) > 0]

    if prices and _option_total_price(option) == min(prices):
        badges.append("Best price")
    if option.get("stops") == 0:
        badges.append("Direct")
    if durations and _duration_to_minutes(option) == min(durations):
        badges.append("Shortest")
    return badges


def _hotel_badges(hotels: list[dict], hotel: dict) -> list[str]:
    badges = []
    prices = [float(item.get("total_price", 0) or 0) for item in hotels if item.get("total_price")]
    ratings = [float(item.get("rating", 0) or 0) for item in hotels if item.get("rating")]

    if prices and float(hotel.get("total_price", 0) or 0) == min(prices):
        badges.append("Best price")
    if ratings and float(hotel.get("rating", 0) or 0) == max(ratings):
        badges.append("Top rated")
    return badges


def _badge_line(badges: list[str]) -> str:
    return " · ".join(badges)


def _format_flight_option_label(
    option: dict,
    options: list[dict],
    currency: str,
    leg_label: str,
    index: int,
) -> str:
    summary_key = "return_summary" if leg_label == "Return" else "outbound_summary"
    badges = _flight_badges(options, option)
    badge_text = f" [{_badge_line(badges)}]" if badges else ""
    return (
        f"Option {index + 1}: {option.get('airline', 'Unknown airline')}{badge_text} | "
        f"{leg_label}: {option.get(summary_key, 'Details unavailable')} | "
        f"{option.get('duration', 'Unknown duration')} | "
        f"{_format_stops(option.get('stops', 0))} | "
        f"{_format_option_price(option, currency)}"
    )


def _format_hotel_option_label(hotel: dict, hotels: list[dict], currency: str, index: int) -> str:
    badges = _hotel_badges(hotels, hotel)
    badge_text = f" [{_badge_line(badges)}]" if badges else ""
    return (
        f"Option {index + 1}: {hotel.get('name', 'Unknown Hotel')}{badge_text} | "
        f"Rating: {hotel.get('rating', '?')} | "
        f"{format_currency(hotel.get('price_per_night', 0), currency)}/night | "
        f"{format_currency(hotel.get('total_price', 0), currency)} total"
    )


def _budget_flight_detail(option: dict, currency: str) -> str:
    """Explain how the selected flight total is calculated."""
    if not option:
        return "Selected itinerary total"

    adults = max(1, int(option.get("adults", 1) or 1))
    per_person = float(option.get("price", 0) or 0)
    if adults > 1 and per_person > 0:
        return f"{adults} traveller(s) × {format_currency(per_person, currency)}/person"
    if per_person > 0 and adults == 1:
        return f"1 traveller × {format_currency(per_person, currency)}"
    return "Selected itinerary total"


def _budget_hotel_detail(hotel: dict, budget: dict, currency: str) -> str:
    """Explain how the selected hotel total is calculated."""
    if not hotel:
        return "Full stay for selected room/search"

    price_per_night = float(hotel.get("price_per_night", 0) or 0)
    nights = max(0, int(budget.get("daily_expense_days", 0) or 0))
    if price_per_night > 0 and nights > 0:
        return f"{nights} night(s) × {format_currency(price_per_night, currency)}/night"
    return "Full stay for selected room/search"


def _compress_star_preferences(stars: list[int]) -> list[int]:
    """Collapse expanded star lists into minimal `N-star and up` thresholds for display."""
    selected = sorted({int(star) for star in stars if star in HOTEL_STARS})
    thresholds: list[int] = []
    covered: set[int] = set()
    for star in selected:
        if star in covered:
            continue
        thresholds.append(star)
        covered.update(range(star, 6))
    return thresholds


def _expand_star_thresholds(thresholds: list[int]) -> list[int]:
    """Expand `N-star and up` thresholds into explicit star values for storage/search."""
    expanded: set[int] = set()
    for threshold in thresholds:
        if threshold in HOTEL_STARS:
            expanded.update(range(int(threshold), 6))
    return sorted(expanded)


def _init_session_state() -> None:
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value

    provider, model = normalise_llm_selection(
        st.session_state.llm_provider,
        st.session_state.llm_model,
    )
    st.session_state.llm_provider = provider
    st.session_state.llm_model = model

def _summarise_token_usage(usage_list: list[dict]) -> dict[str, Any]:
    return {
        "input_tokens": sum(int(item.get("input_tokens", 0) or 0) for item in usage_list),
        "output_tokens": sum(int(item.get("output_tokens", 0) or 0) for item in usage_list),
        "cost": sum(float(item.get("cost", 0) or 0) for item in usage_list),
    }


def _build_token_usage_label(state: dict, index: int | None = None) -> str:
    trip = state.get("trip_request", {})
    destination = trip.get("destination")
    departure = trip.get("departure_date")
    if destination and departure:
        return f"{destination} ({departure})"
    if destination:
        return destination
    if index is not None:
        return f"Search {index}"
    return "Search"


def _token_usage_table_markdown(rows: list[dict[str, str]]) -> str:
    """Render token-usage rows as a single markdown table."""
    lines = [
        "| Search | Input | Output | Cost |",
        "|:---|---:|---:|---:|",
    ]
    for row in rows[:5]:
        lines.append(
            f"| {row['search']} | {row['input']} | {row['output']} | {row['cost']} |"
        )
    return "\n".join(lines)


def _archive_current_token_usage() -> None:
    state = st.session_state.get("graph_state")
    if not state or state.get("_token_usage_archived"):
        return
    usage_list = state.get("token_usage", [])
    if not usage_list:
        return

    summary = _summarise_token_usage(usage_list)
    label = _build_token_usage_label(state, index=len(st.session_state.token_usage_history) + 1)
    st.session_state.token_usage_history.insert(0, {"label": label, **summary})
    st.session_state.token_usage_history = st.session_state.token_usage_history[:5]
    state["_token_usage_archived"] = True


def _append_assistant_message(content: str) -> None:
    st.session_state.messages.append({"role": "assistant", "content": content})


def _reset_trip_flow() -> None:
    logger.info("Resetting trip flow for user_id=%s", st.session_state.user_id)
    _archive_current_token_usage()
    st.session_state.messages = []
    st.session_state.graph_state = None
    st.session_state.awaiting_review = False
    st.session_state.trip_complete = False


def _display_messages() -> None:
    for message in st.session_state.messages:
        if message.get("role") == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def _planning_progress_markdown(lines: list[str]) -> str:
    """Render streaming planning updates as a compact assistant message."""
    return "\n\n".join(lines)


def _run_initial_planning(
    user_message: str,
    structured_fields: dict | None = None,
    free_text_query: str | None = None,
) -> None:
    logger.info(
        "Starting initial planning for user_id=%s provider=%s model=%s",
        st.session_state.user_id,
        st.session_state.llm_provider,
        st.session_state.llm_model,
    )
    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        logger.warning("Selected provider is not ready: %s", provider_message)
        _append_assistant_message(
            f"I can't use the selected provider yet: {provider_message}"
        )
        st.error(provider_message)
        return

    initial_state = {
        "user_id": st.session_state.user_id,
        "llm_provider": st.session_state.llm_provider,
        "llm_model": st.session_state.llm_model,
        "messages": [{"role": "user", "content": user_message}],
        "user_approved": False,
        "user_feedback": "",
    }
    if structured_fields is not None:
        initial_state["structured_fields"] = structured_fields
    if free_text_query:
        initial_state["free_text_query"] = free_text_query

    node_labels = {
        "load_profile": "Loading your traveler profile...",
        "trip_intake": "Understanding your trip request...",
        "flight_search": "Searching flights...",
        "hotel_search": "Searching hotels...",
        "destination_research": "Preparing destination briefing...",
        "aggregate_budget": "Calculating budget breakdown...",
        "review": "Preparing your trip summary...",
    }

    try:
        _archive_current_token_usage()
        result = initial_state.copy()
        progress_lines = ["Planning your trip..."]
        with st.chat_message("assistant"):
            progress_placeholder = st.empty()
            progress_placeholder.markdown(_planning_progress_markdown(progress_lines))
        with st.status("Planning your trip...", expanded=True) as status:
            for event in _get_graph().stream(initial_state):
                for node_name, node_output in event.items():
                    label = node_labels.get(node_name, f"Running {node_name}...")
                    st.write(label)
                    progress_lines.append(f"**{label}**")
                    if node_name != "review":
                        latest_message = next(
                            (
                                message for message in reversed(node_output.get("messages", []))
                                if message.get("role") == "assistant" and message.get("content")
                            ),
                            None,
                        )
                        if latest_message:
                            st.write(latest_message["content"])
                            progress_lines.append(latest_message["content"])
                    progress_placeholder.markdown(_planning_progress_markdown(progress_lines))
                    logger.info("Streaming node completed: %s", node_name)
                    result.update(node_output)
            status.update(label="Trip research complete!", state="complete", expanded=False)
    except Exception as exc:
        logger.exception("Initial planning failed")
        _append_assistant_message(f"I hit an error while planning your trip: {exc}")
        st.error(f"Planning failed: {exc}")
        return

    st.session_state.graph_state = result
    logger.info("Initial planning completed current_step=%s", result.get("current_step"))
    latest_assistant_message = next(
        (
            message for message in reversed(result.get("messages", []))
            if message.get("role") == "assistant" and message.get("content")
        ),
        None,
    )
    if latest_assistant_message:
        st.session_state.messages.append(latest_assistant_message)
        progress_placeholder.markdown(latest_assistant_message["content"])
    st.session_state.awaiting_review = result.get("current_step") == "awaiting_review"


def _run_finalisation(feedback: str = "") -> None:
    state = st.session_state.graph_state
    if not state:
        st.error("No trip data to finalise. Please start a new search.")
        return

    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        logger.warning("Selected provider is not ready for finalisation: %s", provider_message)
        _append_assistant_message(
            f"I can't use the selected provider yet: {provider_message}"
        )
        st.error(provider_message)
        return

    state["user_approved"] = True
    state["user_feedback"] = feedback
    state["llm_provider"] = st.session_state.llm_provider
    state["llm_model"] = st.session_state.llm_model

    try:
        with st.spinner("Generating your final itinerary..."):
            state = run_finalisation(state)
    except Exception as exc:
        logger.exception("Finalisation failed")
        _append_assistant_message(f"I hit an error while generating the itinerary: {exc}")
        st.error(f"Finalisation failed: {exc}")
        return

    st.session_state.graph_state = state
    logger.info("Finalisation completed for user_id=%s", st.session_state.user_id)
    if state.get("final_itinerary"):
        _append_assistant_message(state["final_itinerary"])

    st.session_state.awaiting_review = False
    st.session_state.trip_complete = True


def _render_model_settings() -> None:
    st.header("Model Settings")
    st.caption("Choose which AI powers trip planning and itinerary generation.")

    provider_name = "Google" if st.session_state.llm_provider == "google" else "OpenAI"
    use_google_provider = st.toggle(
        f"Provider: {provider_name}",
        value=st.session_state.llm_provider == "google",
        help="Switch between OpenAI and Google.",
    )
    selected_provider = "google" if use_google_provider else "openai"
    if selected_provider != st.session_state.llm_provider:
        logger.info(
            "Switching provider from %s to %s",
            st.session_state.llm_provider,
            selected_provider,
        )
        st.session_state.llm_provider = selected_provider
        st.session_state.llm_model = get_available_models(selected_provider)[0]
        st.rerun()

    available_models = get_available_models(st.session_state.llm_provider)
    if st.session_state.llm_model not in available_models:
        st.session_state.llm_model = available_models[0]

    provider_name = "Google" if st.session_state.llm_provider == "google" else "OpenAI"
    st.caption(f"Currently using {provider_name}.")

    selected_model = st.selectbox(
        "Model",
        options=available_models,
        index=available_models.index(st.session_state.llm_model),
        format_func=lambda model: MODEL_LABELS.get(model, model),
    )
    if selected_model != st.session_state.llm_model:
        logger.info("Switching model from %s to %s", st.session_state.llm_model, selected_model)
        st.session_state.llm_model = selected_model

    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        st.warning(provider_message)


def _render_token_usage() -> None:
    """Display token usage for the current trip in the sidebar."""
    state = st.session_state.graph_state
    history = st.session_state.get("token_usage_history", [])
    current_summary = None
    current_label = None
    if state and state.get("token_usage"):
        current_summary = _summarise_token_usage(state.get("token_usage", []))
        current_label = _build_token_usage_label(state)

    if not current_summary and not history:
        return

    st.divider()
    headline_cost = current_summary["cost"] if current_summary else history[0]["cost"]
    with st.expander(f"Token Usage — ${headline_cost:.4f}", expanded=False):
        rows = []
        if current_summary:
            rows.append({
                "search": current_label,
                "input": f"{current_summary['input_tokens']:,}",
                "output": f"{current_summary['output_tokens']:,}",
                "cost": f"${current_summary['cost']:.4f}",
            })
        for item in history:
            rows.append({
                "search": item["label"],
                "input": f"{item['input_tokens']:,}",
                "output": f"{item['output_tokens']:,}",
                "cost": f"${item['cost']:.4f}",
            })

        st.markdown(_token_usage_table_markdown(rows))


def _render_profile_sidebar() -> None:
    st.divider()
    st.header("Profile Manager")

    with st.expander("Create Profile", expanded=False):
        with st.form("profile_create_form"):
            new_user_id = st.text_input(
                "New Profile ID",
                value="",
                help="Create a new traveler profile saved under this id.",
            ).strip()
            create_submitted = st.form_submit_button("Create Profile")

        if create_submitted:
            if not new_user_id:
                st.warning("Enter a profile id to create.")
            else:
                save_profile(new_user_id, load_profile(new_user_id))
                st.session_state.user_id = new_user_id
                st.success(f"Profile `{new_user_id}` is ready.")
                st.rerun()

    profile = load_profile(st.session_state.user_id)

    st.caption(f"Editing profile `{st.session_state.user_id}`.")

    with st.expander("Edit Profile", expanded=False):
        with st.form("profile_form"):
            saved_city = profile.get("home_city", "")
            home_city = st.selectbox(
                "Home City",
                options=CITIES if saved_city in CITIES else [saved_city] + CITIES,
                index=0 if saved_city == "" else (
                    CITIES.index(saved_city) if saved_city in CITIES else 0
                ),
            )
            saved_country = profile.get("passport_country", "")
            passport_country = st.selectbox(
                "Passport Country",
                options=COUNTRIES if saved_country in COUNTRIES else [saved_country] + COUNTRIES,
                index=0 if saved_country == "" else (
                    COUNTRIES.index(saved_country) if saved_country in COUNTRIES else 0
                ),
            )
            travel_class = st.selectbox(
                "Preferred Class",
                options=TRAVEL_CLASSES,
                index=TRAVEL_CLASSES.index(profile.get("travel_class", "ECONOMY")),
            )
            saved_airlines = profile.get("preferred_airlines", [])
            preferred_airlines = st.multiselect(
                "Preferred Airlines",
                options=AIRLINES,
                default=[a for a in saved_airlines if a in AIRLINES],
            )
            saved_hotel_stars = profile.get("preferred_hotel_stars", [])
            saved_hotel_star_thresholds = _compress_star_preferences(saved_hotel_stars)
            preferred_hotel_stars = st.multiselect(
                "Preferred Hotel Stars",
                options=HOTEL_STARS,
                default=[star for star in saved_hotel_star_thresholds if star in HOTEL_STARS],
                format_func=lambda star: f"{star}-star and up",
                help="Choose one or more default hotel tiers like `3-star and up`.",
                placeholder="Select preferred hotel tiers",
            )
            saved_outbound_window = profile.get("preferred_outbound_time_window", [0, 23])
            preferred_outbound_time_window = st.slider(
                "Preferred Outbound Flight Time",
                min_value=0,
                max_value=23,
                value=(saved_outbound_window[0], saved_outbound_window[1]),
                format="%02d:00",
                help="Default departure-time window for outbound flights.",
            )
            saved_return_window = profile.get("preferred_return_time_window", [0, 23])
            preferred_return_time_window = st.slider(
                "Preferred Return Flight Time",
                min_value=0,
                max_value=23,
                value=(saved_return_window[0], saved_return_window[1]),
                format="%02d:00",
                help="Default departure-time window for return flights.",
            )
            submitted = st.form_submit_button("Save Profile")

        if submitted:
            updated_profile = {
                **profile,
                "home_city": home_city,
                "passport_country": passport_country,
                "travel_class": travel_class,
                "preferred_airlines": preferred_airlines,
                "preferred_hotel_stars": _expand_star_thresholds(preferred_hotel_stars),
                "preferred_outbound_time_window": list(preferred_outbound_time_window),
                "preferred_return_time_window": list(preferred_return_time_window),
            }
            save_profile(st.session_state.user_id, updated_profile)
            st.success("Profile saved.")

    if profile.get("past_trips"):
        st.subheader("Past Trips")
        for trip in profile["past_trips"][-5:]:
            st.write(f"• {trip['destination']} ({trip.get('dates', '')})")

    st.divider()
    if st.button("New Trip", use_container_width=True):
        _reset_trip_flow()
        st.rerun()


def _render_review_actions() -> None:
    state = st.session_state.graph_state
    if not state:
        return

    flights = state.get("flight_options", [])[:5]
    hotels = state.get("hotel_options", [])[:5]
    budget = state.get("budget", {})
    currency = normalise_currency(
        budget.get("currency") or state.get("trip_request", {}).get("currency")
    )
    flights_removed_by_budget = (
        budget.get("flights_before_budget_filter", 0) > 0
        and budget.get("flights_after_budget_filter", 0) == 0
    )
    hotels_removed_by_budget = (
        budget.get("hotels_before_budget_filter", 0) > 0
        and budget.get("hotels_after_budget_filter", 0) == 0
    )

    # ── Flight selection ──
    trip_request = state.get("trip_request", {})
    is_round_trip = bool(trip_request.get("return_date"))
    trip_type_label = "Round Trip" if is_round_trip else "One-Way"
    st.subheader(f"✈️ Select a Flight ({trip_type_label})")
    if is_round_trip:
        st.caption(
            "Step 1: choose an outbound flight. Step 2: choose a matching return flight for that outbound option."
        )
    else:
        st.caption("Choose the outbound flight you want included in the itinerary.")
    if flights:
        flight_labels = []
        for idx, flight in enumerate(flights):
            flight_labels.append(_format_flight_option_label(flight, flights, currency, "Outbound", idx))
        selected_flight_idx = st.radio(
            "Outbound options",
            options=range(len(flights)),
            format_func=lambda i: flight_labels[i],
            index=0,
        )
    else:
        if flights_removed_by_budget:
            st.warning("Flights were found, but none fit the selected total trip budget.")
        else:
            st.warning("No flights found. Try different dates or cities.")
        selected_flight_idx = None

    selected_outbound = flights[selected_flight_idx] if selected_flight_idx is not None else {}
    return_options = []
    selected_return_idx = None
    if is_round_trip and selected_outbound:
        st.subheader("↩️ Select a Return Flight")
        st.caption("Return options are loaded for the outbound flight selected above.")
        departure_token = selected_outbound.get("departure_token", "")
        if departure_token:
            user_profile = state.get("user_profile", {})
            return_time_window = _normalise_time_window(
                user_profile.get("preferred_return_time_window")
            )
            with st.spinner("Loading return flight options..."):
                return_options = _get_return_flight_options(
                    origin=trip_request.get("origin", ""),
                    destination=trip_request.get("destination", ""),
                    departure_date=trip_request.get("departure_date", ""),
                    return_date=trip_request.get("return_date", ""),
                    departure_token=departure_token,
                    adults=trip_request.get("num_travelers", 1),
                    travel_class=trip_request.get("travel_class", "ECONOMY"),
                    currency=currency,
                    return_time_window=return_time_window,
                )

            if return_options:
                return_labels = []
                for idx, option in enumerate(return_options):
                    return_labels.append(
                        _format_flight_option_label(option, return_options, currency, "Return", idx)
                    )
                selected_return_idx = st.radio(
                    "Return options",
                    options=range(len(return_options)),
                    format_func=lambda i: return_labels[i],
                    index=0,
                )
                st.success("Return flight selected and paired with your outbound choice.")
            else:
                st.warning(
                    "No return flights were found for this outbound option. Choose another outbound flight above to load a different return set."
                )
        elif selected_outbound.get("return_details_available"):
            st.info(f"Return: {selected_outbound.get('return_summary')}")
        else:
            st.warning("This outbound option does not include a token for loading return flights.")

    # ── Hotel selection ──
    st.subheader("🏨 Select a Hotel")
    st.caption("Hotel totals use the destination dates and traveller count from your trip request.")
    if hotels:
        hotel_labels = []
        for idx, h in enumerate(hotels):
            hotel_labels.append(_format_hotel_option_label(h, hotels, currency, idx))
        selected_hotel_idx = st.radio(
            "Hotel options",
            options=range(len(hotels)),
            format_func=lambda i: hotel_labels[i],
            index=0,
        )
    else:
        if hotels_removed_by_budget:
            st.warning("Hotels were found, but none fit the selected total trip budget.")
        else:
            st.warning("No hotels found. Try different dates or destination.")
        selected_hotel_idx = None

    # ── Budget summary ──
    if budget:
        st.subheader("💰 Budget Summary")
        st.caption("Estimated totals for the currently selected options, with a simple cost breakdown for each category.")
        sel_return = return_options[selected_return_idx] if selected_return_idx is not None else {}
        sel_flight = _combine_round_trip_flight(selected_outbound, sel_return) if sel_return else selected_outbound
        sel_flight_price = sel_flight.get("total_price", sel_flight.get("price", 0)) if sel_flight else 0
        selected_hotel = hotels[selected_hotel_idx] if selected_hotel_idx is not None else {}
        sel_hotel_price = selected_hotel.get("total_price", 0) if selected_hotel else 0
        daily_expenses = budget.get("estimated_daily_expenses", 0)
        daily_days = budget.get("daily_expense_days", 0)
        daily_travelers = budget.get("daily_expense_travelers", 0)
        daily_rate = budget.get("daily_expense_per_traveler", 0)
        flight_label = "Flight"
        if sel_flight.get("adults", 1) > 1:
            flight_label = f"Flight ({sel_flight['adults']} travellers)"
        daily_expense_detail = "Estimated meals, local transport, and incidentals"
        if daily_travelers and daily_days and daily_rate:
            daily_expense_detail = (
                f"{daily_travelers} traveller(s) × {daily_days} day(s) × "
                f"{format_currency(daily_rate, currency)}/day"
            )
        flight_detail = _budget_flight_detail(sel_flight, currency)
        hotel_detail = _budget_hotel_detail(selected_hotel, budget, currency)
        total = sel_flight_price + sel_hotel_price + daily_expenses

        budget_md = (
            "| Category | What It Covers | Amount |\n"
            "|:---|:---|---:|\n"
            f"| ✈️ {flight_label} | {flight_detail} | {format_currency(sel_flight_price, currency)} |\n"
            f"| 🏨 Hotel | {hotel_detail} | {format_currency(sel_hotel_price, currency)} |\n"
            f"| 🍽️ Daily expenses | {daily_expense_detail} | {format_currency(daily_expenses, currency)} |\n"
            f"| **🧳 Total** | **Selected trip estimate** | **{format_currency(total, currency)}** |"
        )
        st.markdown(budget_md)

        budget_limit = trip_request.get("budget_limit", 0) or 0
        if budget_limit > 0:
            remaining = budget_limit - total
            if remaining >= 0:
                st.success(f"Selected options are within budget with {format_currency(remaining, currency)} to spare.")
            else:
                st.warning(f"Selected options are over budget by {format_currency(abs(remaining), currency)}.")

        if budget.get("budget_notes"):
            st.info(f"📝 {budget['budget_notes']}")

    st.divider()

    # ── Actions ──
    feedback = st.text_input(
        "Final itinerary notes (optional)",
        placeholder="e.g. Make it relaxed, add vegetarian tips, mention window seat preference",
        help="These notes guide the final itinerary text. They do not re-run flight or hotel search.",
    )

    flight_selection_complete = (
        selected_flight_idx is not None
        and (
            not is_round_trip
            or selected_return_idx is not None
            or selected_outbound.get("return_details_available")
        )
    )
    flight_selection_required = selected_flight_idx is not None
    can_approve = (
        (not flight_selection_required or flight_selection_complete)
        and (flight_selection_complete or selected_hotel_idx is not None)
    )
    if is_round_trip and selected_flight_idx is not None and not flight_selection_complete:
        st.warning("Choose a return flight before approving this round trip.")
    if st.button(
        "Approve & Generate Itinerary",
        type="primary",
        use_container_width=True,
        disabled=not can_approve,
    ):
        selected_return = return_options[selected_return_idx] if selected_return_idx is not None else {}
        if selected_return:
            state["selected_flight"] = _combine_round_trip_flight(selected_outbound, selected_return)
        elif flight_selection_complete:
            state["selected_flight"] = selected_outbound
        else:
            state["selected_flight"] = {}
        state["selected_hotel"] = hotels[selected_hotel_idx] if selected_hotel_idx is not None else {}
        st.session_state.graph_state = state
        st.session_state.messages.append(
            {"role": "user", "content": "Approved! Please generate my final itinerary."}
        )
        _run_finalisation(feedback=feedback)
        st.rerun()


def _build_trip_message(fields: dict) -> str:
    """Compose a natural-language trip request from structured form fields."""
    parts = []
    currency = normalise_currency(fields.get("currency"))
    if fields.get("origin") and fields.get("destination"):
        parts.append(f"Fly from {fields['origin']} to {fields['destination']}")
    elif fields.get("destination"):
        parts.append(f"Trip to {fields['destination']}")

    if fields.get("departure_date") and fields.get("return_date"):
        parts.append(f"from {fields['departure_date']} to {fields['return_date']}")
    elif fields.get("departure_date"):
        parts.append(f"departing {fields['departure_date']} (one-way)")

    if fields.get("num_travelers", 1) > 1:
        parts.append(f"for {fields['num_travelers']} travelers")

    if fields.get("budget_limit"):
        parts.append(f"budget {format_currency(fields['budget_limit'], currency)}")

    if fields.get("preferences"):
        parts.append(f"({fields['preferences']})")

    return ", ".join(parts) + "."


def _build_structured_fields_from_form(
    *,
    free_text: str,
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date | None,
    one_way: bool,
    num_nights: int | None,
    num_travelers: int,
    budget_limit: int | float,
    currency: str,
    preferences: str,
    default_origin: str,
    default_departure_date: date,
    default_return_date: date,
    default_currency: str,
) -> dict[str, Any]:
    """Build structured form fields, ignoring untouched defaults when free text is present."""
    has_free_text = bool(free_text.strip())
    fields: dict[str, Any] = {}

    if origin and (not has_free_text or origin != default_origin):
        fields["origin"] = origin
    if destination:
        fields["destination"] = destination
    if num_travelers > 1:
        fields["num_travelers"] = num_travelers
    if budget_limit > 0:
        fields["budget_limit"] = budget_limit
    if preferences:
        fields["preferences"] = preferences
    if not has_free_text or currency != default_currency:
        fields["currency"] = currency

    if one_way:
        if not has_free_text or departure_date != default_departure_date or (num_nights or 7) != 7:
            fields["departure_date"] = str(departure_date)
            check_out = departure_date + timedelta(days=num_nights or 7)
            fields["check_out_date"] = str(check_out)
    else:
        if (
            not has_free_text
            or departure_date != default_departure_date
            or return_date != default_return_date
        ):
            fields["departure_date"] = str(departure_date)
            if return_date is not None:
                fields["return_date"] = str(return_date)

    return fields


def _render_trip_form() -> None:
    """Render the trip request form with free-text primary input and optional structured fields."""
    saved_profiles = list_profiles()
    if not saved_profiles:
        saved_profiles = [st.session_state.user_id]
    if st.session_state.user_id not in saved_profiles:
        saved_profiles = [st.session_state.user_id, *saved_profiles]

    selected_user_id = st.selectbox(
        "Traveler Profile",
        options=saved_profiles,
        index=saved_profiles.index(st.session_state.user_id),
        help="Choose which saved profile to use for this search.",
    )
    if selected_user_id != st.session_state.user_id:
        st.session_state.user_id = selected_user_id
        st.rerun()

    profile = load_profile(st.session_state.user_id)
    default_origin = profile.get("home_city", "")

    st.caption(f"Planning this trip with profile `{st.session_state.user_id}`.")

    st.subheader("Plan Your Trip")

    # Primary input: free-text query
    free_text = st.text_area(
        "Describe your trip",
        placeholder="e.g. I want to fly from London to Tokyo, June 10-17, budget $3000, direct flights only",
        help="Type your trip request in plain English. You can also use the fields below to be more specific.",
        height=100,
    )

    # Optional structured fields for refinement
    default_departure_date = date.today() + timedelta(days=14)
    default_return_date = date.today() + timedelta(days=21)
    default_currency = normalise_currency(DEFAULT_CURRENCY)
    with st.expander("Refine your search (optional)"):
        col1, col2 = st.columns(2)
        with col1:
            origin_options = [""] + (CITIES if default_origin in CITIES else [default_origin] + CITIES)
            origin = st.selectbox(
                "From (Origin City)",
                options=origin_options,
                index=origin_options.index(default_origin) if default_origin in origin_options else 0,
                help="Leave blank to use the origin from your text above.",
            )
        with col2:
            destination_options = [""] + DESTINATIONS
            destination = st.selectbox(
                "To (Destination City)",
                options=destination_options,
                index=0,
                help="Leave blank to use the destination from your text above.",
            )

        one_way = st.checkbox(
            "One-way trip",
            value=st.session_state.get("one_way_saved", False),
            on_change=lambda: st.session_state.update(
                one_way_saved=st.session_state["one_way_widget"]
            ),
            key="one_way_widget",
        )

        col3, col4 = st.columns(2)
        with col3:
            departure_date = st.date_input(
                "Departure Date",
                value=default_departure_date,
                min_value=date.today(),
            )
        with col4:
            if one_way:
                num_nights = st.number_input(
                    "Number of Nights",
                    min_value=1,
                    max_value=90,
                    value=7,
                    help="How many nights at your destination.",
                )
            else:
                return_date = st.date_input(
                    "Return Date",
                    value=default_return_date,
                    min_value=date.today(),
                )

        col5, col6, col7 = st.columns(3)
        with col5:
            num_travelers = st.number_input(
                "Travelers", min_value=1, max_value=10, value=1,
            )
        with col6:
            budget_limit = st.number_input(
                "Budget (0 = flexible)", min_value=0, max_value=100000, value=0, step=500,
            )
        with col7:
            currency = st.selectbox(
                "Currency",
                options=CURRENCIES,
                index=CURRENCIES.index(default_currency),
            )

        preferences = st.text_input(
            "Special Requests (optional)",
            placeholder="e.g. direct flights only, near city centre",
        )

    submitted = st.button(
        "Search Flights & Hotels", type="primary", use_container_width=True,
    )

    if submitted:
        has_free_text = bool(free_text.strip())
        fields = _build_structured_fields_from_form(
            free_text=free_text,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date if not one_way else None,
            one_way=one_way,
            num_nights=num_nights if one_way else None,
            num_travelers=num_travelers,
            budget_limit=budget_limit,
            currency=currency,
            preferences=preferences,
            default_origin=default_origin,
            default_departure_date=default_departure_date,
            default_return_date=default_return_date,
            default_currency=default_currency,
        )
        has_structured = bool(fields)

        if not has_free_text and not has_structured:
            st.warning("Please describe your trip or fill in at least a destination.")
            return

        if not one_way and return_date <= departure_date:
            st.warning("Return date must be after departure date.")
            return

        # Build display message
        if has_free_text:
            user_message = free_text.strip()
        else:
            user_message = _build_trip_message(fields)

        st.session_state.messages.append({"role": "user", "content": user_message})
        _run_initial_planning(
            user_message,
            structured_fields=fields if has_structured else None,
            free_text_query=free_text.strip() if has_free_text else None,
        )
        st.rerun()


def _render_main_area() -> None:
    st.title("TripBreeze AI")
    st.caption(
        "Describe your trip below and I'll find flights, hotels, and destination info for you."
    )
    _display_messages()

    if st.session_state.trip_complete:
        st.success("Your trip itinerary is ready. Click New Trip in the sidebar to plan another.")
        return

    if st.session_state.awaiting_review:
        _render_review_actions()
        return

    _render_trip_form()


def main() -> None:
    _init_session_state()

    with st.sidebar:
        _render_model_settings()
        _render_token_usage()
        _render_profile_sidebar()

    _render_main_area()
