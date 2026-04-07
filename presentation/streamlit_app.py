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
    "awaiting_review": False,
    "trip_complete": False,
    "user_id": "default_user",
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
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


def _append_assistant_message(content: str) -> None:
    st.session_state.messages.append({"role": "assistant", "content": content})


def _reset_trip_flow() -> None:
    logger.info("Resetting trip flow for user_id=%s", st.session_state.user_id)
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
        "research": "Researching flights, hotels, and destination info...",
        "aggregate_budget": "Calculating budget breakdown...",
        "review": "Preparing your trip summary...",
    }

    try:
        result = initial_state.copy()
        with st.status("Planning your trip...", expanded=True) as status:
            for event in _get_graph().stream(initial_state):
                for node_name, node_output in event.items():
                    label = node_labels.get(node_name, f"Running {node_name}...")
                    st.write(label)
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
    st.session_state.awaiting_review = True


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
    model_labels = {
        "gpt-4o-mini": "OpenAI GPT-4o mini",
        "gpt-4.1-mini": "OpenAI GPT-4.1 mini",
        "gpt-4.1-nano": "OpenAI GPT-4.1 nano",
        "gpt-3.5-turbo": "OpenAI GPT-3.5 Turbo",
        "gemini-2.5-flash": "Google Gemini 2.5 Flash",
        "gemini-2.5-flash-lite": "Google Gemini 2.5 Flash-Lite",
    }

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
        format_func=lambda model: model_labels.get(model, model),
    )
    if selected_model != st.session_state.llm_model:
        logger.info("Switching model from %s to %s", st.session_state.llm_model, selected_model)
        st.session_state.llm_model = selected_model

    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        st.warning(provider_message)


def _render_token_usage() -> None:
    """Display accumulated token usage and estimated cost in the sidebar."""
    state = st.session_state.graph_state
    if not state:
        return
    usage_list = state.get("token_usage", [])
    if not usage_list:
        return

    total_input = sum(u.get("input_tokens", 0) for u in usage_list)
    total_output = sum(u.get("output_tokens", 0) for u in usage_list)
    total_cost = sum(u.get("cost", 0) for u in usage_list)

    st.divider()
    with st.expander(f"Token Usage — ${total_cost:.4f}", expanded=False):
        st.caption(
            f"**Tokens:** {total_input:,} in / {total_output:,} out\n\n"
            f"**Est. cost (USD):** ${total_cost:.4f}"
        )
        for entry in usage_list:
            st.caption(
                f"{entry.get('node', '?')} ({entry.get('model', '?')}): "
                f"{entry.get('input_tokens', 0):,} in / "
                f"{entry.get('output_tokens', 0):,} out — "
                f"${entry.get('cost', 0):.4f}"
            )


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
    if flights:
        flight_labels = []
        for f in flights:
            stops = "Direct" if f["stops"] == 0 else f"{f['stops']} stop(s)"
            price_label = format_currency(f.get("total_price", f["price"]), currency)
            if f.get("adults", 1) > 1:
                price_label += f" ({format_currency(f['price'], currency)}/person)"
            flight_labels.append(
                f"{f.get('airline', '?')} — Outbound: {f['outbound_summary']} — {f['duration']} — {stops} — {price_label}"
            )
        selected_flight_idx = st.radio(
            "Choose an outbound flight",
            options=range(len(flights)),
            format_func=lambda i: flight_labels[i],
            index=0,
            label_visibility="collapsed",
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
                for option in return_options:
                    stops = "Direct" if option["stops"] == 0 else f"{option['stops']} stop(s)"
                    price_label = format_currency(option.get("total_price", option["price"]), currency)
                    if option.get("adults", 1) > 1:
                        price_label += f" ({format_currency(option['price'], currency)}/person)"
                    return_labels.append(
                        f"{option.get('airline', '?')} — Return: {option['return_summary']} — {option['duration']} — {stops} — {price_label}"
                    )
                selected_return_idx = st.radio(
                    "Choose a return flight",
                    options=range(len(return_options)),
                    format_func=lambda i: return_labels[i],
                    index=0,
                    label_visibility="collapsed",
                )
            else:
                st.warning("No return flights were found for the selected outbound option. Try another outbound flight.")
        elif selected_outbound.get("return_details_available"):
            st.info(f"Return: {selected_outbound.get('return_summary')}")
        else:
            st.warning("This outbound option does not include a token for loading return flights.")

    # ── Hotel selection ──
    st.subheader("🏨 Select a Hotel")
    if hotels:
        hotel_labels = []
        for h in hotels:
            hotel_labels.append(
                f"{h['name']} — ⭐ {h.get('rating', '?')} — {format_currency(h['price_per_night'], currency)}/night — {format_currency(h['total_price'], currency)} total"
            )
        selected_hotel_idx = st.radio(
            "Choose a hotel",
            options=range(len(hotels)),
            format_func=lambda i: hotel_labels[i],
            index=0,
            label_visibility="collapsed",
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
        sel_return = return_options[selected_return_idx] if selected_return_idx is not None else {}
        sel_flight = _combine_round_trip_flight(selected_outbound, sel_return) if sel_return else selected_outbound
        sel_flight_price = sel_flight.get("total_price", sel_flight.get("price", 0)) if sel_flight else 0
        sel_hotel_price = hotels[selected_hotel_idx]["total_price"] if selected_hotel_idx is not None else 0
        daily_expenses = budget.get("estimated_daily_expenses", 0)
        daily_expense_label = "Daily Expenses (est.)"
        if budget.get("daily_expense_travelers") and budget.get("daily_expense_days"):
            daily_expense_label = (
                f"Daily Expenses (est., {budget['daily_expense_travelers']} "
                f"traveler(s) × {budget['daily_expense_days']} day(s))"
            )
        total = sel_flight_price + sel_hotel_price + daily_expenses

        budget_md = (
            "| Category | Amount |\n"
            "|:---|---:|\n"
            f"| ✈️ Flight | {format_currency(sel_flight_price, currency)} |\n"
            f"| 🏨 Hotel | {format_currency(sel_hotel_price, currency)} |\n"
            f"| 🍽️ {daily_expense_label} | {format_currency(daily_expenses, currency)} |\n"
            f"| **🧳 Total** | **{format_currency(total, currency)}** |"
        )
        st.markdown(budget_md)

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
    can_approve = flight_selection_complete or selected_hotel_idx is not None
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
                value=date.today() + timedelta(days=14),
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
                    value=date.today() + timedelta(days=21),
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
            default_currency = normalise_currency(DEFAULT_CURRENCY)
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
        # Build structured fields from the form (only include non-empty values)
        fields: dict[str, Any] = {}
        if origin:
            fields["origin"] = origin
        if destination:
            fields["destination"] = destination
        if num_travelers > 1:
            fields["num_travelers"] = num_travelers
        if budget_limit > 0:
            fields["budget_limit"] = budget_limit
        fields["currency"] = currency
        if preferences:
            fields["preferences"] = preferences

        has_free_text = bool(free_text.strip())
        has_structured = bool(fields.get("origin") or fields.get("destination"))

        if not has_free_text and not has_structured:
            st.warning("Please describe your trip or fill in at least a destination.")
            return

        # Always include dates from the form (they have sensible defaults)
        fields["departure_date"] = str(departure_date)
        if one_way:
            # No return flight, but compute a check-out date for hotel search
            check_out = departure_date + timedelta(days=num_nights)
            fields["check_out_date"] = str(check_out)
        else:
            fields["return_date"] = str(return_date)
            if return_date <= departure_date:
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
