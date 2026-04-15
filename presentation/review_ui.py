"""Review and selection UI for flights and hotels."""

import html

import streamlit as st

from presentation import api_client
from infrastructure.currency_utils import format_currency, normalise_currency


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


_BADGE_COLORS = {
    "Best price": ("#14532d", "#bbf7d0"),
    "Direct": ("#1d4ed8", "#bfdbfe"),
    "Shortest": ("#581c87", "#e9d5ff"),
    "Top rated": ("#78350f", "#fde68a"),
}


def _badge_pills_html(badges: list[str]) -> str:
    pills = []
    for badge in badges:
        background, foreground = _BADGE_COLORS.get(badge, ("#374151", "#e5e7eb"))
        pills.append(
            f"<span style='display:inline-block;margin-right:0.4rem;margin-bottom:0.35rem;"
            f"padding:0.18rem 0.55rem;border-radius:999px;background:{background};"
            f"color:{foreground};font-size:0.82rem;font-weight:600;'>{html.escape(badge)}</span>"
        )
    return "".join(pills)


def _render_option_card(title: str, badges: list[str], details: list[str]) -> str:
    details_html = "".join(
        f"<div style='margin-top:0.25rem;color:#d1d5db;'>{detail if detail.startswith(('🔗 <a', '<a')) else html.escape(detail)}</div>"
        for detail in details
        if detail
    )
    badges_html = _badge_pills_html(badges)
    badges_block = f"<div style='margin-top:0.5rem;'>{badges_html}</div>" if badges_html else ""
    return (
        "<div style='padding:0.9rem 1rem;margin:0.45rem 0 0.7rem 0;border:1px solid #374151;"
        "border-radius:0.85rem;background:#111827;'>"
        f"<div style='font-weight:700;color:#f9fafb;'>{html.escape(title)}</div>"
        f"{badges_block}"
        f"{details_html}"
        "</div>"
    )


def _normalise_selected_index(selected_index: int | None, num_options: int) -> int | None:
    """Return a safe selected index for a fixed-size option list."""
    if num_options <= 0:
        return None
    if selected_index is None:
        return 0
    return selected_index if 0 <= selected_index < num_options else 0


def _selection_button_label(is_selected: bool) -> str:
    return "◉ Selected" if is_selected else "○ Select"


def render_selectable_cards(
    *,
    selection_key: str,
    cards: list[dict[str, object]],
) -> int | None:
    """Render simple selectable cards and return the chosen index."""
    selected_index = _normalise_selected_index(st.session_state.get(selection_key), len(cards))
    if selected_index is not None:
        st.session_state[selection_key] = selected_index

    for index, card in enumerate(cards):
        is_selected = index == selected_index
        with st.container():
            content_col, action_col = st.columns([8, 2], vertical_alignment="center")
            with content_col:
                st.markdown(
                    _render_option_card(
                        title=str(card["title"]),
                        badges=list(card["badges"]),
                        details=list(card["details"]),
                    ),
                    unsafe_allow_html=True,
                )
            with action_col:
                if st.button(
                    _selection_button_label(is_selected),
                    key=f"{selection_key}_{index}",
                    type="primary" if is_selected else "secondary",
                    use_container_width=True,
                ):
                    if index != selected_index:
                        st.session_state[selection_key] = index
                        st.rerun()

    return selected_index


def flight_option_cards(options: list[dict], currency: str, leg_label: str) -> list[dict[str, object]]:
    summary_key = "return_summary" if leg_label == "Return" else "outbound_summary"
    cards = []
    for index, option in enumerate(options):
        details = [
            f"{leg_label}: {option.get(summary_key, 'Details unavailable')}",
            f"Duration: {option.get('duration', 'Unknown duration')} · {_format_stops(option.get('stops', 0))}",
            f"Price: {_format_option_price(option, currency)}",
        ]
        booking_url = option.get("booking_url")
        if booking_url:
            details.append(f"🔗 <a href='{html.escape(booking_url)}' target='_blank' style='color:#60a5fa;'>View on Google Flights</a>")
        cards.append({
            "title": f"Option {index + 1}: {option.get('airline', 'Unknown airline')}",
            "badges": _flight_badges(options, option),
            "details": details,
        })
    return cards


def hotel_option_cards(hotels: list[dict], currency: str) -> list[dict[str, object]]:
    cards = []
    for index, hotel in enumerate(hotels):
        hotel_class = hotel.get("hotel_class")
        stars_str = ("⭐" * hotel_class) if hotel_class else None
        details = []
        if stars_str:
            details.append(f"Stars: {stars_str} ({hotel_class}-star)")
        details.append(f"Rating: {hotel.get('rating', '?')}")
        details.append(f"Per night: {format_currency(hotel.get('price_per_night', 0), currency)}")
        details.append(f"Total: {format_currency(hotel.get('total_price', 0), currency)}")
        booking_url = hotel.get("booking_url")
        if booking_url:
            details.append(f"🔗 <a href='{html.escape(booking_url)}' target='_blank' style='color:#60a5fa;'>View on Google Hotels</a>")
        cards.append({
            "title": f"Option {index + 1}: {hotel.get('name', 'Unknown Hotel')}",
            "badges": _hotel_badges(hotels, hotel),
            "details": details,
        })
    return cards


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
    return api_client.fetch_return_flights(
        thread_id=st.session_state.get("thread_id", ""),
        params={
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
            "departure_token": departure_token,
            "adults": adults,
            "travel_class": travel_class,
            "currency": currency,
            "return_time_window": list(return_time_window) if return_time_window else None,
        },
    )


def _can_approve_itinerary(
    *,
    is_round_trip: bool,
    selected_flight_idx: int | None,
    selected_hotel_idx: int | None,
    selected_return_idx: int | None,
    selected_outbound: dict,
) -> bool:
    """Require both flight and hotel selections before approval."""
    flight_ready = selected_flight_idx is not None and (
        not is_round_trip
        or selected_return_idx is not None
        or selected_outbound.get("return_details_available")
    )
    hotel_ready = selected_hotel_idx is not None
    return flight_ready and hotel_ready


def _is_budget_status_note(note: str) -> bool:
    """Detect notes that only repeat within/over-budget status already shown in the UI."""
    lowered = note.strip().lower()
    return "within budget" in lowered or "exceeds your budget" in lowered or "to spare" in lowered


def _render_multi_city_review(state: dict) -> None:
    """Render per-leg selection UI for multi-city trips."""
    trip_legs = state.get("trip_legs", [])
    flight_options_by_leg = state.get("flight_options_by_leg", [])
    hotel_options_by_leg = state.get("hotel_options_by_leg", [])
    budget = state.get("budget", {})
    trip_request = state.get("trip_request", {})
    currency = normalise_currency(
        budget.get("currency") or trip_request.get("currency")
    )

    st.subheader("🌍 Multi-City Trip Selection")
    st.caption(
        "Select a flight and hotel (where needed) for each leg of your trip."
    )

    selected_flights: list[dict] = []
    selected_hotels: list[dict] = []
    all_selections_complete = True

    for leg in trip_legs:
        leg_idx = leg.get("leg_index", 0)
        origin = leg.get("origin", "?")
        destination = leg.get("destination", "?")
        departure_date = leg.get("departure_date", "?")
        nights = leg.get("nights", 0)
        needs_hotel = leg.get("needs_hotel", False)

        # Leg header
        leg_label = f"Leg {leg_idx + 1}: {origin} → {destination}"
        if nights > 0:
            leg_label += f" ({nights} night{'s' if nights != 1 else ''})"
        else:
            leg_label += " (Return)"

        with st.expander(leg_label, expanded=(leg_idx == 0)):
            st.markdown(f"**📅 Departure:** {departure_date}")

            # Flight selection for this leg
            leg_flights = flight_options_by_leg[leg_idx] if leg_idx < len(flight_options_by_leg) else []
            if leg_flights:
                st.markdown("**✈️ Flight Options:**")
                flight_idx = render_selectable_cards(
                    selection_key=f"selected_flight_leg_{leg_idx}",
                    cards=flight_option_cards(leg_flights[:5], currency, "Outbound"),
                )
                if flight_idx is not None:
                    selected_flights.append(leg_flights[flight_idx])
                else:
                    selected_flights.append({})
                    all_selections_complete = False
            else:
                st.warning("No flights found for this leg.")
                selected_flights.append({})
                all_selections_complete = False

            # Hotel selection if needed
            if needs_hotel:
                leg_hotels = hotel_options_by_leg[leg_idx] if leg_idx < len(hotel_options_by_leg) else []
                if leg_hotels:
                    st.markdown("**🏨 Hotel Options:**")
                    hotel_idx = render_selectable_cards(
                        selection_key=f"selected_hotel_leg_{leg_idx}",
                        cards=hotel_option_cards(leg_hotels[:5], currency),
                    )
                    if hotel_idx is not None:
                        selected_hotels.append(leg_hotels[hotel_idx])
                    else:
                        selected_hotels.append({})
                        all_selections_complete = False
                else:
                    st.warning("No hotels found for this destination.")
                    selected_hotels.append({})
                    all_selections_complete = False
            else:
                st.info("No hotel needed for this leg (return flight).")
                selected_hotels.append({})

    # Budget summary for multi-city
    if budget:
        st.subheader("💰 Budget Summary")

        # Calculate totals from selections
        total_flight_cost = sum(
            f.get("total_price", f.get("price", 0)) for f in selected_flights if f
        )
        total_hotel_cost = sum(
            h.get("total_price", 0) for h in selected_hotels if h
        )
        daily_expenses = budget.get("estimated_daily_expenses", 0)
        total = total_flight_cost + total_hotel_cost + daily_expenses

        budget_md = (
            "| Category | Amount |\n"
            "|:---|---:|\n"
            f"| ✈️ Flights ({len(trip_legs)} legs) | {format_currency(total_flight_cost, currency)} |\n"
            f"| 🏨 Hotels | {format_currency(total_hotel_cost, currency)} |\n"
            f"| 🍽️ Daily expenses | {format_currency(daily_expenses, currency)} |\n"
            f"| **🧳 Total** | **{format_currency(total, currency)}** |"
        )
        st.markdown(budget_md)

        budget_limit = trip_request.get("budget_limit", 0) or 0
        if budget_limit > 0:
            remaining = budget_limit - total
            if remaining >= 0:
                st.success(f"Selected options are within budget with {format_currency(remaining, currency)} to spare.")
            else:
                st.warning(f"Selected options are over budget by {format_currency(abs(remaining), currency)}.")

    st.divider()

    # Approve button
    if not all_selections_complete:
        st.warning("Please select a flight and hotel for each leg before approving.")

    if st.button(
        "Approve Selections",
        type="primary",
        use_container_width=True,
        disabled=not all_selections_complete,
    ):
        state["selected_flights"] = selected_flights
        state["selected_hotels"] = selected_hotels
        # Backward compat: populate legacy fields with first leg
        state["selected_flight"] = selected_flights[0] if selected_flights else {}
        state["selected_hotel"] = selected_hotels[0] if selected_hotels else {}
        st.session_state.graph_state = state
        st.session_state.awaiting_review = False
        st.session_state.awaiting_interests = True
        st.rerun()


def render_review_actions() -> None:
    state = st.session_state.graph_state
    if not state:
        return

    # Check for multi-city trip
    trip_legs = state.get("trip_legs", [])
    if trip_legs:
        _render_multi_city_review(state)
        return

    # Single-destination trip: existing UI
    st.caption(
        "Review the options below, choose your preferred flight and hotel, then approve to generate the final itinerary."
    )

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

    # Flight selection
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
        selected_flight_idx = render_selectable_cards(
            selection_key="selected_outbound_option_index",
            cards=flight_option_cards(flights, currency, "Outbound"),
        )
    else:
        if flights_removed_by_budget:
            st.warning("Flights were found, but none fit the selected total trip budget.")
        else:
            st.warning("No flights found. Try different dates or cities.")
        selected_flight_idx = None
        st.session_state.pop("selected_outbound_option_index", None)

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
                selected_return_idx = render_selectable_cards(
                    selection_key="selected_return_option_index",
                    cards=flight_option_cards(return_options, currency, "Return"),
                )
                st.success("Return flight selected and paired with your outbound choice.")
            else:
                st.warning(
                    "No return flights were found for this outbound option. Choose another outbound flight above to load a different return set."
                )
                st.session_state.pop("selected_return_option_index", None)
        elif selected_outbound.get("return_details_available"):
            st.info(f"Return: {selected_outbound.get('return_summary')}")
            st.session_state.pop("selected_return_option_index", None)
        else:
            st.warning("This outbound option does not include a token for loading return flights.")
            st.session_state.pop("selected_return_option_index", None)
    else:
        st.session_state.pop("selected_return_option_index", None)

    # Hotel selection
    st.subheader("🏨 Select a Hotel")
    st.caption("Hotel totals use the destination dates and traveller count from your trip request.")
    if hotels:
        selected_hotel_idx = render_selectable_cards(
            selection_key="selected_hotel_option_index",
            cards=hotel_option_cards(hotels, currency),
        )
    else:
        if hotels_removed_by_budget:
            st.warning("Hotels were found, but none fit the selected total trip budget.")
        else:
            st.warning("No hotels found. Try different dates or destination.")
        selected_hotel_idx = None
        st.session_state.pop("selected_hotel_option_index", None)

    # Budget summary
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

        if budget.get("budget_notes") and not _is_budget_status_note(str(budget["budget_notes"])):
            st.info(f"📝 {budget['budget_notes']}")

    st.divider()

    # Actions
    flight_selection_complete = selected_flight_idx is not None and (
        not is_round_trip
        or selected_return_idx is not None
        or selected_outbound.get("return_details_available")
    )
    can_approve = _can_approve_itinerary(
        is_round_trip=is_round_trip,
        selected_flight_idx=selected_flight_idx,
        selected_hotel_idx=selected_hotel_idx,
        selected_return_idx=selected_return_idx,
        selected_outbound=selected_outbound,
    )
    if is_round_trip and selected_flight_idx is not None and not flight_selection_complete:
        st.warning("Choose a return flight before approving this round trip.")
    if st.button(
        "Approve Selections",
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
        st.session_state.awaiting_review = False
        st.session_state.awaiting_interests = True
        st.rerun()
