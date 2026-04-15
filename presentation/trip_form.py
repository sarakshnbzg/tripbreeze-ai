"""Trip request form rendering and field processing."""

from datetime import date, timedelta
from typing import Any

import streamlit as st

from config import CITIES, CURRENCIES, DEFAULT_CURRENCY, DESTINATIONS
from infrastructure.currency_utils import format_currency, normalise_currency
from infrastructure.persistence.memory_store import load_profile


def build_trip_message(fields: dict) -> str:
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
    if fields.get("stops") == 0:
        parts.append("(direct flights only)")

    return ", ".join(parts) + "."


def build_structured_fields_from_form(
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
    direct_only: bool,
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
    if direct_only:
        fields["stops"] = 0
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


def parse_num_nights(raw_value: str) -> int | None:
    """Parse a one-way stay length entered in the form."""
    text = raw_value.strip()
    if not text:
        return None
    try:
        nights = int(text)
    except ValueError:
        return None
    return nights if nights > 0 else None


def render_trip_form() -> None:
    """Render the trip request form with free-text primary input and optional structured fields."""
    from presentation.planning_flow import run_initial_planning

    profile = load_profile(st.session_state.user_id)
    default_origin = profile.get("home_city", "")

    st.subheader("Plan Your Trip")

    # Primary input: free-text query + mic button on the right
    from presentation.mic_button import mic_button
    text_col, mic_col = st.columns([0.9, 0.1], vertical_alignment="bottom")

    with text_col:
        free_text = st.text_area(
            "Describe your trip",
            value=st.session_state.get("trip_description", ""),
            placeholder="e.g. I want to fly from London to Tokyo, June 10-17, budget $3000, direct flights only",
            help="Type your trip request in plain English, or click the mic to use voice input.",
            height=100,
        )
        st.session_state["trip_description"] = free_text

    with mic_col:
        mic_button()

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

        col5a, col5b = st.columns(2)
        with col5a:
            direct_only = st.checkbox(
                "Direct flights only",
                help="Only show nonstop flights.",
            )
        with col5b:
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
                raw_num_nights = st.text_input(
                    "Number of Nights",
                    value="",
                    help="Required for one-way trips so hotel search and budget can be calculated.",
                    placeholder="e.g. 5",
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
        num_nights = parse_num_nights(raw_num_nights) if one_way else None
        fields = build_structured_fields_from_form(
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
            direct_only=direct_only,
            default_origin=default_origin,
            default_departure_date=default_departure_date,
            default_return_date=default_return_date,
            default_currency=default_currency,
        )
        has_structured = bool(fields)

        if not has_free_text and not has_structured:
            st.warning("Please describe your trip or fill in at least a destination.")
            return

        if not has_free_text and not fields.get("destination"):
            st.warning("Please select a destination or describe your trip in the text box above.")
            return

        if not one_way and return_date <= departure_date:
            st.warning("Return date must be after departure date.")
            return
        if one_way and num_nights is None and not has_free_text:
            st.warning("One-way trips require the number of nights so hotel search and budget can be calculated.")
            return

        # Build display message
        if has_free_text:
            user_message = free_text.strip()
        else:
            user_message = build_trip_message(fields)

        st.session_state.messages.append({"role": "user", "content": user_message})
        run_initial_planning(
            user_message,
            structured_fields=fields if has_structured else None,
            free_text_query=free_text.strip() if has_free_text else None,
        )
        st.rerun()
