"""Streamlit UI for TripBreeze AI.

Dependency direction: presentation -> application -> domain -> infrastructure
This module is a thin UI client that calls the FastAPI backend via api_client.
It does not import graph or domain-layer code directly.
"""

import streamlit as st

from typing import Any

from config import (
    AIRLINES,
    CITIES,
    COUNTRIES,
    HOTEL_STARS,
    TRAVEL_CLASSES,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_SENDER_EMAIL,
    SMTP_SENDER_PASSWORD,
    SMTP_USE_TLS,
)
from infrastructure.currency_utils import format_currency
from infrastructure.logging_utils import get_logger
from infrastructure.llms.model_factory import (
    get_available_models,
    get_provider_status,
    normalise_llm_selection,
)
from infrastructure.persistence.memory_store import (
    load_profile,
    save_profile,
    register_user,
    verify_user,
)
from infrastructure.pdf_generator import generate_trip_pdf
from infrastructure.email_sender import send_itinerary_email, SMTPConfig

from presentation.planning_flow import (
    run_clarification,
    run_finalisation,
    inject_booking_links,
)
from presentation.review_ui import render_review_actions
from presentation.trip_form import render_trip_form

logger = get_logger(__name__)

st.set_page_config(page_title="TripBreeze AI", page_icon="✈️", layout="wide")


SESSION_DEFAULTS = {
    "messages": [],
    "graph_state": None,
    "token_usage_history": [],
    "awaiting_review": False,
    "awaiting_interests": False,
    "awaiting_clarification": False,
    "clarification_question": "",
    "trip_complete": False,
    "user_id": "default_user",
    "authenticated": False,
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
    "llm_temperature": 0.3,
    "thread_id": "",
}

MODEL_LABELS = {
    "gpt-4o-mini": "OpenAI GPT-4o mini",
    "gpt-4.1-mini": "OpenAI GPT-4.1 mini",
    "gpt-4.1-nano": "OpenAI GPT-4.1 nano",
    "gpt-3.5-turbo": "OpenAI GPT-3.5 Turbo",
    "gemini-2.5-flash": "Google Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Google Gemini 2.5 Flash-Lite",
}


def _planning_progress_markdown(updates: list[str]) -> str:
    """Format streamed planning updates into a readable markdown block."""
    return "\n\n".join(update for update in updates if update)


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


def _render_login_screen() -> None:
    """Show a login / register form and block until the user authenticates."""
    st.title("Welcome to TripBreeze AI")

    login_tab, register_tab = st.tabs(["Log In", "Register"])

    with login_tab:
        with st.form("login_form"):
            login_id = st.text_input("Username").strip()
            login_pw = st.text_input("Password", type="password")
            login_submitted = st.form_submit_button("Log In")
        if login_submitted:
            if not login_id or not login_pw:
                st.warning("Please enter both username and password.")
            elif verify_user(login_id, login_pw):
                st.session_state.user_id = login_id
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with register_tab:
        with st.form("register_form"):
            reg_id = st.text_input("Choose a Username").strip()
            reg_pw = st.text_input("Choose a Password", type="password")
            reg_pw2 = st.text_input("Confirm Password", type="password")
            reg_submitted = st.form_submit_button("Register")
        if reg_submitted:
            if not reg_id or not reg_pw:
                st.warning("Please fill in all fields.")
            elif reg_pw != reg_pw2:
                st.error("Passwords do not match.")
            elif len(reg_pw) < 4:
                st.error("Password must be at least 4 characters.")
            elif register_user(reg_id, reg_pw):
                st.session_state.user_id = reg_id
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error(f"Username `{reg_id}` is already taken.")


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


def _reset_trip_flow() -> None:
    logger.info("Resetting trip flow for user_id=%s", st.session_state.user_id)
    _archive_current_token_usage()
    st.session_state.messages = []
    st.session_state.graph_state = None
    st.session_state.awaiting_review = False
    st.session_state.awaiting_interests = False
    st.session_state.awaiting_clarification = False
    st.session_state.clarification_question = ""
    st.session_state.trip_complete = False
    st.session_state.thread_id = ""


def _display_messages() -> None:
    for message in st.session_state.messages:
        if message.get("role") == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


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

    selected_temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=float(st.session_state.llm_temperature),
        step=0.1,
        help=(
            "Controls creativity. Lower values (0.0) give deterministic, focused outputs "
            "suited to structured extraction; higher values (1.0) produce more varied, "
            "creative itineraries."
        ),
    )
    if selected_temperature != st.session_state.llm_temperature:
        logger.info(
            "Switching temperature from %s to %s",
            st.session_state.llm_temperature,
            selected_temperature,
        )
        st.session_state.llm_temperature = selected_temperature

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

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "search": st.column_config.TextColumn("Search"),
                "input": st.column_config.TextColumn("Input"),
                "output": st.column_config.TextColumn("Output"),
                "cost": st.column_config.TextColumn("Cost"),
            },
        )


def _render_profile_sidebar() -> None:
    st.divider()
    st.header("My Profile")

    profile = load_profile(st.session_state.user_id)

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
        for idx, trip in enumerate(profile["past_trips"][-5:]):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"• {trip['destination']} ({trip.get('dates', '')})")
            with col2:
                if trip.get("final_itinerary"):
                    try:
                        pdf_bytes = generate_trip_pdf(
                            final_itinerary=trip["final_itinerary"],
                            graph_state=trip.get("pdf_state", {}),
                        )
                        st.download_button(
                            label="📥 PDF",
                            data=pdf_bytes,
                            file_name=f"{trip['destination'].replace(' ', '_')}_itinerary.pdf",
                            mime="application/pdf",
                            key=f"past_trip_pdf_{idx}",
                        )
                    except Exception:
                        pass
    st.divider()
    if st.button("New Trip", use_container_width=True):
        _reset_trip_flow()
        st.rerun()


def _render_interests_form() -> None:
    """Separate step after flight/hotel approval - choose interests and pace."""
    state = st.session_state.graph_state
    if not state:
        st.error("No trip data found. Please start a new search.")
        return

    trip_request = state.get("trip_request", {})
    destination = trip_request.get("destination", "your destination")

    st.subheader(f"Personalise your {destination} itinerary")
    st.caption(
        "Pick the activities you enjoy and your preferred daily pace. "
        "We'll find real attractions and build a day-by-day plan for you."
    )

    interest_options = ["food", "history", "nature", "art", "nightlife", "shopping", "outdoors", "family"]
    existing_interests = trip_request.get("interests", []) or []
    interests = st.multiselect(
        "What do you enjoy while travelling?",
        options=interest_options,
        default=[i for i in existing_interests if i in interest_options],
        key="interests_form_interests",
    )

    pace_options = ["relaxed", "moderate", "packed"]
    existing_pace = trip_request.get("pace") or "moderate"
    pace = st.radio(
        "Daily pace",
        options=pace_options,
        index=pace_options.index(existing_pace) if existing_pace in pace_options else 1,
        horizontal=True,
        key="interests_form_pace",
        help="Relaxed ≈ 2 activities/day · Moderate ≈ 3 · Packed ≈ 4+",
    )

    feedback = st.text_input(
        "Final itinerary notes (optional)",
        placeholder="e.g. add vegetarian tips, mention window seat preference",
        help="These notes guide the final itinerary text.",
    )

    if st.button("Generate Itinerary", type="primary", use_container_width=True):
        updated_trip = dict(trip_request)
        updated_trip["interests"] = list(interests)
        updated_trip["pace"] = pace
        state["trip_request"] = updated_trip
        st.session_state.graph_state = state
        st.session_state.messages.append(
            {"role": "user", "content": "Approved! Please generate my final itinerary."}
        )
        run_finalisation(feedback=feedback)
        st.session_state.awaiting_interests = False
        st.rerun()


def _render_clarification_input() -> None:
    """Render a chat input for the user to answer a clarification question."""
    answer = st.chat_input("Type your answer...")
    if answer:
        st.session_state.messages.append({"role": "user", "content": answer})
        with st.chat_message("user"):
            st.markdown(answer)
        run_clarification(answer)
        st.rerun()


def _render_main_area() -> None:
    st.title("TripBreeze AI")
    st.caption(
        "Describe your trip below and I'll find flights, hotels, and destination info for you."
    )
    _display_messages()

    if st.session_state.trip_complete:
        st.success("Your trip itinerary is ready. Click New Trip in the sidebar to plan another.")

        if st.session_state.graph_state:
            final_itinerary = st.session_state.graph_state.get("final_itinerary", "")
            if final_itinerary:
                try:
                    pdf_bytes = generate_trip_pdf(
                        final_itinerary=final_itinerary,
                        graph_state=st.session_state.graph_state,
                    )
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="📥 Download Itinerary as PDF",
                            data=pdf_bytes,
                            file_name="trip_itinerary.pdf",
                            mime="application/pdf",
                        )

                    with col2:
                        with st.form("email_form", border=False):
                            email_input = st.text_input(
                                "📧 Email itinerary",
                                placeholder="your.email@example.com",
                                label_visibility="collapsed",
                            )
                            submitted = st.form_submit_button("Send", use_container_width=True)

                            if submitted:
                                if not email_input:
                                    st.error("Please enter an email address.")
                                else:
                                    smtp_config = SMTPConfig(
                                        smtp_host=SMTP_HOST,
                                        smtp_port=SMTP_PORT,
                                        sender_email=SMTP_SENDER_EMAIL,
                                        sender_password=SMTP_SENDER_PASSWORD,
                                        use_tls=SMTP_USE_TLS,
                                    )

                                    with st.spinner("Sending email..."):
                                        success, message = send_itinerary_email(
                                            recipient_email=email_input,
                                            pdf_bytes=pdf_bytes,
                                            smtp_config=smtp_config,
                                            recipient_name=st.session_state.user_id,
                                        )

                                    if success:
                                        st.success(message)
                                        logger.info("Itinerary emailed to %s", email_input)
                                    else:
                                        st.error(message)
                                        logger.warning("Failed to email itinerary: %s", message)

                except Exception as e:
                    logger.exception("Failed to generate PDF")
                    st.warning(f"Could not generate PDF: {e}")
        return

    if st.session_state.awaiting_review:
        render_review_actions()
        return

    if st.session_state.awaiting_interests:
        _render_interests_form()
        return

    if st.session_state.awaiting_clarification:
        _render_clarification_input()
        return

    render_trip_form()


def _logout() -> None:
    st.session_state.authenticated = False
    st.session_state.user_id = "default_user"
    _reset_trip_flow()


def main() -> None:
    _init_session_state()

    if not st.session_state.authenticated:
        _render_login_screen()
        return

    with st.sidebar:
        st.caption(f"Logged in as **{st.session_state.user_id}**")
        if st.button("Log Out"):
            _logout()
            st.rerun()
        _render_model_settings()
        _render_token_usage()
        _render_profile_sidebar()

    _render_main_area()
