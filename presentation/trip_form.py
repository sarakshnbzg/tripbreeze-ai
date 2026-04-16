"""Trip request form rendering and field processing."""

from datetime import date, timedelta
from typing import Any

import streamlit as st

from config import CURRENCIES, DEFAULT_CURRENCY
from infrastructure.currency_utils import format_currency, normalise_currency
from infrastructure.persistence.memory_store import load_profile, list_reference_values


def build_trip_message(fields: dict) -> str:
    """Compose a natural-language trip request from structured form fields."""
    parts = []
    currency = normalise_currency(fields.get("currency"))

    # Multi-city trip message
    if fields.get("multi_city_legs"):
        legs = fields["multi_city_legs"]
        origin = fields.get("origin", "")
        if origin:
            parts.append(f"Starting from {origin}:")
        leg_descriptions = [f"{leg['destination']} for {leg['nights']} nights" for leg in legs if leg.get("destination")]
        parts.append(", then ".join(leg_descriptions))
        if fields.get("departure_date"):
            parts.append(f"departing {fields['departure_date']}")
        if fields.get("return_to_origin") is False:
            parts.append("(one-way, not returning to origin)")
    else:
        # Single destination
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
    multi_city: bool = False,
    multi_city_legs: list[dict] | None = None,
    multi_city_return_to_origin: bool = True,
) -> dict[str, Any]:
    """Build structured form fields, ignoring untouched defaults when free text is present."""
    has_free_text = bool(free_text.strip())
    fields: dict[str, Any] = {}

    if origin and (not has_free_text or origin != default_origin):
        fields["origin"] = origin

    # Multi-city: include legs instead of single destination
    if multi_city and multi_city_legs:
        valid_legs = [leg for leg in multi_city_legs if leg.get("destination")]
        if valid_legs:
            fields["multi_city_legs"] = valid_legs
            fields["return_to_origin"] = multi_city_return_to_origin
    elif destination:
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

    # Date handling
    if multi_city:
        # Multi-city: only departure date, return is calculated
        if not has_free_text or departure_date != default_departure_date:
            fields["departure_date"] = str(departure_date)
    elif one_way:
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
            placeholder="e.g. London to Tokyo, June 10-17, budget $3000 — or multi-city: Paris 3 days, then Barcelona 4 days",
            help="Type your trip request in plain English, or click the mic to use voice input. Multi-city trips are automatically detected.",
            height=100,
        )
        st.session_state["trip_description"] = free_text

    with mic_col:
        mic_button()

    # Optional structured fields for refinement
    default_departure_date = date.today() + timedelta(days=14)
    default_return_date = date.today() + timedelta(days=21)
    default_currency = normalise_currency(DEFAULT_CURRENCY)
    cities = list_reference_values("cities")
    destinations = cities
    with st.expander("Refine your search (optional)"):
        # Trip type options first (they affect other fields)
        opt_col1, opt_col2, opt_col3 = st.columns(3)
        with opt_col1:
            multi_city = st.checkbox(
                "Multi-city trip",
                value=st.session_state.get("multi_city_saved", False),
                on_change=lambda: st.session_state.update(
                    multi_city_saved=st.session_state["multi_city_widget"]
                ),
                key="multi_city_widget",
                help="Plan a trip visiting multiple destinations (e.g., Paris then Barcelona).",
            )
        with opt_col2:
            one_way = st.checkbox(
                "One-way trip",
                value=st.session_state.get("one_way_saved", False),
                on_change=lambda: st.session_state.update(
                    one_way_saved=st.session_state["one_way_widget"]
                ),
                key="one_way_widget",
                help=(
                    "For multi-city, skip the final return leg back to origin (open-jaw)."
                    if multi_city
                    else None
                ),
            )
        with opt_col3:
            direct_only = st.checkbox(
                "Direct flights only",
                help="Only show nonstop flights.",
            )

        # Origin and destination
        origin_options = [""] + (cities if default_origin in cities else [default_origin] + cities)
        if multi_city:
            origin = st.selectbox(
                "From (Origin City)",
                options=origin_options,
                index=origin_options.index(default_origin) if default_origin in origin_options else 0,
                help="Leave blank to use the origin from your text above.",
            )
            destination = ""  # Not used for multi-city

            st.markdown("**Add destinations in order of visit:**")

            # Initialize multi-city legs in session state
            if "multi_city_legs" not in st.session_state:
                st.session_state.multi_city_legs = [{"destination": "", "nights": 3}]

            legs = st.session_state.multi_city_legs
            destination_options = [""] + destinations

            for i, leg in enumerate(legs):
                leg_col1, leg_col2, leg_col3 = st.columns([3, 2, 1])
                with leg_col1:
                    leg["destination"] = st.selectbox(
                        f"Destination {i + 1}",
                        options=destination_options,
                        index=destination_options.index(leg["destination"]) if leg["destination"] in destination_options else 0,
                        key=f"mc_dest_{i}",
                    )
                with leg_col2:
                    leg["nights"] = st.number_input(
                        f"Nights",
                        min_value=1,
                        max_value=30,
                        value=leg.get("nights", 3),
                        key=f"mc_nights_{i}",
                    )
                with leg_col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if len(legs) > 1 and st.button("✕", key=f"mc_remove_{i}", help="Remove this destination"):
                        legs.pop(i)
                        st.rerun()

            if len(legs) < 5:
                if st.button("+ Add another destination", key="mc_add"):
                    legs.append({"destination": "", "nights": 3})
                    st.rerun()

            st.session_state.multi_city_legs = legs
        else:
            # Single destination: origin and destination side by side
            loc_col1, loc_col2 = st.columns(2)
            with loc_col1:
                origin = st.selectbox(
                    "From (Origin City)",
                    options=origin_options,
                    index=origin_options.index(default_origin) if default_origin in origin_options else 0,
                    help="Leave blank to use the origin from your text above.",
                )
            with loc_col2:
                destination_options = [""] + destinations
                destination = st.selectbox(
                    "To (Destination City)",
                    options=destination_options,
                    index=0,
                    help="Leave blank to use the destination from your text above.",
                )

        # Dates
        date_col1, date_col2 = st.columns(2, vertical_alignment="bottom")
        with date_col1:
            departure_date = st.date_input(
                "Departure Date",
                value=default_departure_date,
                min_value=date.today(),
            )
        with date_col2:
            if multi_city:
                st.info("Return date is calculated from your destinations and nights.")
                return_date = None
                raw_num_nights = ""
            elif one_way:
                raw_num_nights = st.text_input(
                    "Number of Nights",
                    value="",
                    help="Required for one-way trips so hotel search and budget can be calculated.",
                    placeholder="e.g. 5",
                )
                return_date = None
            else:
                return_date = st.date_input(
                    "Return Date",
                    value=default_return_date,
                    min_value=date.today(),
                )
                raw_num_nights = ""

        # Travelers and budget
        budget_col1, budget_col2, budget_col3 = st.columns(3)
        with budget_col1:
            num_travelers = st.number_input(
                "Travelers", min_value=1, max_value=10, value=1,
            )
        with budget_col2:
            budget_limit = st.number_input(
                "Budget (0 = flexible)", min_value=0, max_value=100000, value=0, step=500,
            )
        with budget_col3:
            currency = st.selectbox(
                "Currency",
                options=CURRENCIES,
                index=CURRENCIES.index(default_currency),
            )

        preferences = st.text_input(
            "Special Requests (optional)",
            placeholder="e.g. near city centre, wheelchair accessible",
        )

    submitted = st.button(
        "Search Flights & Hotels", type="primary", use_container_width=True,
    )

    if submitted:
        has_free_text = bool(free_text.strip())
        # one_way for single-destination means no return flight + nights input;
        # for multi-city it means open-jaw (no return-to-origin leg).
        num_nights = parse_num_nights(raw_num_nights) if (one_way and not multi_city) else None

        # Get multi-city legs if in multi-city mode
        mc_legs = st.session_state.get("multi_city_legs", []) if multi_city else None

        fields = build_structured_fields_from_form(
            free_text=free_text,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date if not one_way and not multi_city else None,
            one_way=one_way and not multi_city,
            num_nights=num_nights,
            num_travelers=num_travelers,
            budget_limit=budget_limit,
            currency=currency,
            preferences=preferences,
            direct_only=direct_only,
            default_origin=default_origin,
            default_departure_date=default_departure_date,
            default_return_date=default_return_date,
            default_currency=default_currency,
            multi_city=multi_city,
            multi_city_legs=mc_legs,
            multi_city_return_to_origin=not one_way,
        )
        has_structured = bool(fields)

        if not has_free_text and not has_structured:
            st.warning("Please describe your trip or fill in at least a destination.")
            return

        # Validation for multi-city
        if multi_city and not has_free_text:
            valid_legs = [leg for leg in (mc_legs or []) if leg.get("destination")]
            if not valid_legs:
                st.warning("Please add at least one destination for your multi-city trip.")
                return

        # Validation for single destination
        if not multi_city and not has_free_text and not fields.get("destination"):
            st.warning("Please select a destination or describe your trip in the text box above.")
            return

        if not multi_city and not one_way and return_date and return_date <= departure_date:
            st.warning("Return date must be after departure date.")
            return
        if one_way and not multi_city and num_nights is None and not has_free_text:
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
