"""Tests for presentation helper functions across UI modules."""

from datetime import date

from presentation.streamlit_app import (
    _build_token_usage_label,
    _build_profile_payload,
    _logout,
    _personalisation_destination_label,
    _planning_progress_markdown,
    _select_options_with_blank,
    _start_authenticated_session,
    _summarise_token_usage,
)
from presentation.review_ui import (
    _badge_pills_html,
    _can_approve_itinerary,
    _is_budget_status_note,
    _normalise_selected_index,
    _render_option_card,
    _selection_button_label,
    flight_option_cards,
    hotel_option_cards,
)
from presentation.planning_flow import inject_booking_links
from presentation.trip_form import (
    build_structured_fields_from_form,
    parse_num_nights,
)


class TestSummariseTokenUsage:
    def test_returns_total_input_output_and_cost(self):
        usage = [
            {
                "node": "trip_intake",
                "model": "gpt-4o-mini",
                "input_tokens": 100,
                "output_tokens": 20,
                "cost": 0.001,
            },
            {
                "node": "research_orchestrator",
                "model": "gpt-4o-mini",
                "input_tokens": 50,
                "output_tokens": 10,
                "cost": 0.0005,
            },
            {
                "node": "trip_finaliser",
                "model": "gemini-2.5-flash",
                "input_tokens": 200,
                "output_tokens": 40,
                "cost": 0.002,
            },
        ]

        summary = _summarise_token_usage(usage)

        assert summary["input_tokens"] == 350
        assert summary["output_tokens"] == 70
        assert summary["cost"] == 0.0035


class TestBuildTokenUsageLabel:
    def test_uses_destination_and_departure_date(self):
        state = {"trip_request": {"destination": "London", "departure_date": "2026-04-20"}}
        assert _build_token_usage_label(state) == "London (2026-04-20)"

    def test_falls_back_to_search_index(self):
        assert _build_token_usage_label({}, index=2) == "Search 2"


class TestProfileHelpers:
    def test_select_options_with_blank_preserves_empty_choice(self):
        options = _select_options_with_blank("", ["Berlin", "Paris"])

        assert options[0] == ""
        assert options[1:] == ["Berlin", "Paris"]

    def test_select_options_with_blank_includes_saved_custom_value_once(self):
        options = _select_options_with_blank("Munich", ["Berlin", "Paris"])

        assert options == ["", "Munich", "Berlin", "Paris"]

    def test_build_profile_payload_normalises_profile_fields(self):
        payload = _build_profile_payload(
            {"user_id": "alice", "past_trips": []},
            {
                "home_city": "Berlin",
                "passport_country": "Germany",
                "travel_class": "BUSINESS",
                "preferred_airlines": ["Lufthansa"],
                "preferred_hotel_stars": [3],
                "preferred_outbound_time_window": (6, 12),
                "preferred_return_time_window": (14, 20),
            },
        )

        assert payload["home_city"] == "Berlin"
        assert payload["passport_country"] == "Germany"
        assert payload["travel_class"] == "BUSINESS"
        assert payload["preferred_airlines"] == ["Lufthansa"]
        assert payload["preferred_hotel_stars"] == [3, 4, 5]
        assert payload["preferred_outbound_time_window"] == [6, 12]
        assert payload["preferred_return_time_window"] == [14, 20]


class TestPlanningProgressMarkdown:
    def test_joins_updates_with_blank_lines(self):
        content = _planning_progress_markdown(["Planning your trip...", "**Searching flights...**", "Found 5 flight options."])
        assert content == "Planning your trip...\n\n**Searching flights...**\n\nFound 5 flight options."


class TestInjectBookingLinks:
    def test_inserts_single_trip_booking_links(self):
        markdown = "#### 🛫 Flight Details\nFlight info\n\n#### 🏨 Hotel Details\nHotel info"

        updated = inject_booking_links(
            markdown,
            {"airline": "Air France", "booking_url": "https://flights.example/af"},
            {"name": "Hotel Le Marais", "booking_url": "https://hotels.example/marais"},
        )

        assert "[Book Air France on Google Flights](https://flights.example/af)" in updated
        assert "[Book Hotel Le Marais](https://hotels.example/marais)" in updated

    def test_inserts_multi_city_booking_links_per_leg(self):
        markdown = (
            "#### ✈️ Trip Overview\nOverview\n\n"
            "#### 🗺️ Trip Legs\n\n"
            "**Leg 1: London → Paris**\n\n"
            "- 📅 2026-05-01\n\n"
            "- ✈️ Air France\n\n"
            "- 🏨 Hotel Le Marais\n\n"
            "**Leg 2: Paris → Barcelona**\n\n"
            "- 📅 2026-05-04\n\n"
            "- ✈️ Vueling\n\n"
            "- 🏨 Hotel Arts"
        )

        updated = inject_booking_links(
            markdown,
            {},
            {},
            [
                {"airline": "Air France", "booking_url": "https://flights.example/paris"},
                {"airline": "Vueling", "booking_url": "https://flights.example/barcelona"},
            ],
            [
                {"name": "Hotel Le Marais", "booking_url": "https://hotels.example/paris"},
                {"name": "Hotel Arts", "booking_url": "https://hotels.example/barcelona"},
            ],
        )

        assert "**Leg 1: London → Paris**" in updated
        assert "[Book Air France on Google Flights](https://flights.example/paris)" in updated
        assert "[Book Hotel Le Marais](https://hotels.example/paris)" in updated
        assert "[Book Vueling on Google Flights](https://flights.example/barcelona)" in updated
        assert "[Book Hotel Arts](https://hotels.example/barcelona)" in updated


class TestPersonalisationDestinationLabel:
    def test_uses_all_multi_city_destinations_with_overnight_stays(self):
        label = _personalisation_destination_label(
            {
                "trip_request": {"destination": "Paris"},
                "trip_legs": [
                    {"destination": "Paris", "nights": 3},
                    {"destination": "Barcelona", "nights": 4},
                    {"destination": "London", "nights": 0},
                ],
            }
        )

        assert label == "Paris + Barcelona"

    def test_falls_back_to_trip_request_destination_for_single_city(self):
        label = _personalisation_destination_label(
            {"trip_request": {"destination": "Paris"}}
        )

        assert label == "Paris"


class TestOptionCardRendering:
    def test_badge_pills_html_uses_badge_labels(self):
        html_content = _badge_pills_html(["Best price", "Direct"])
        assert "Best price" in html_content
        assert "Direct" in html_content
        assert "border-radius:999px" in html_content

    def test_render_option_card_includes_title_badges_and_details(self):
        card_html = _render_option_card(
            title="Option 1: easyJet",
            badges=["Best price", "Direct"],
            details=["Outbound: BER -> CDG", "Price: EUR 117 total"],
        )
        assert "Option 1: easyJet" in card_html
        assert "Best price" in card_html
        assert "Outbound: BER -&gt; CDG" in card_html
        assert "Price: EUR 117 total" in card_html

    def test_selection_button_label_changes_with_state(self):
        assert _selection_button_label(True) == "◉ Selected"
        assert _selection_button_label(False) == "○ Select"

    def test_normalise_selected_index_defaults_to_first_option(self):
        assert _normalise_selected_index(None, 3) == 0
        assert _normalise_selected_index(9, 3) == 0
        assert _normalise_selected_index(1, 3) == 1
        assert _normalise_selected_index(None, 0) is None

    def test_normalise_selected_index_can_allow_no_selection(self):
        assert _normalise_selected_index(None, 3, default_to_first=False) is None
        assert _normalise_selected_index(9, 3, default_to_first=False) is None
        assert _normalise_selected_index(1, 3, default_to_first=False) == 1

    def test_flight_option_cards_build_display_data(self):
        cards = flight_option_cards(
            [
                {
                    "airline": "easyJet",
                    "outbound_summary": "BER 08:35 -> CDG 10:25",
                    "duration": "1h 50m",
                    "stops": 0,
                    "total_price": 117,
                    "price": 58,
                    "adults": 2,
                }
            ],
            "EUR",
            "Outbound",
        )
        assert cards[0]["title"] == "Option 1: easyJet"
        assert "Best price" in cards[0]["badges"]
        assert "Direct" in cards[0]["badges"]

    def test_hotel_option_cards_build_display_data(self):
        cards = hotel_option_cards(
            [
                {
                    "name": "Hotel Lumiere",
                    "address": "12 Rue de Rivoli, Paris",
                    "amenities": ["Free breakfast", "Pool"],
                    "rating": 9.1,
                    "price_per_night": 120,
                    "total_price": 360,
                }
            ],
            "EUR",
        )
        assert cards[0]["title"] == "Option 1: Hotel Lumiere"
        assert "Rating: 9.1 (Excellent)" in cards[0]["details"][0]
        assert "Address: 12 Rue de Rivoli, Paris" in cards[0]["details"][1]
        assert "Breakfast included" in cards[0]["details"][2]


class TestBuildStructuredFieldsFromForm:
    def test_ignores_untouched_defaults_when_free_text_is_present(self):
        result = build_structured_fields_from_form(
            free_text="I want to fly from Berlin to London on the 20th of April for 2 days. Plan my trip.",
            origin="Berlin",
            destination="",
            departure_date=date(2026, 4, 22),
            return_date=date(2026, 4, 29),
            one_way=False,
            num_nights=None,
            num_travelers=1,
            budget_limit=0,
            currency="EUR",
            preferences="",
            direct_only=False,
            default_origin="Berlin",
            default_departure_date=date(2026, 4, 22),
            default_return_date=date(2026, 4, 29),
            default_currency="EUR",
        )

        assert result == {}

    def test_keeps_explicit_refinements_with_free_text(self):
        result = build_structured_fields_from_form(
            free_text="Plan my trip to London.",
            origin="Berlin",
            destination="London",
            departure_date=date(2026, 4, 24),
            return_date=date(2026, 4, 27),
            one_way=False,
            num_nights=None,
            num_travelers=2,
            budget_limit=1200,
            currency="USD",
            preferences="direct flights only",
            direct_only=False,
            default_origin="Berlin",
            default_departure_date=date(2026, 4, 22),
            default_return_date=date(2026, 4, 29),
            default_currency="EUR",
        )

        assert result["destination"] == "London"
        assert result["departure_date"] == "2026-04-24"
        assert result["return_date"] == "2026-04-27"
        assert result["num_travelers"] == 2
        assert result["budget_limit"] == 1200
        assert result["currency"] == "USD"


class TestParseNumNights:
    def test_parses_positive_integer(self):
        assert parse_num_nights("5") == 5

    def test_rejects_blank_value(self):
        assert parse_num_nights("") is None

    def test_rejects_non_numeric_value(self):
        assert parse_num_nights("five") is None

    def test_rejects_zero_or_negative_values(self):
        assert parse_num_nights("0") is None
        assert parse_num_nights("-2") is None


class TestCanApproveItinerary:
    def test_requires_flight_and_hotel_for_one_way(self):
        assert _can_approve_itinerary(
            is_round_trip=False,
            selected_flight_idx=0,
            selected_hotel_idx=0,
            selected_return_idx=None,
            selected_outbound={},
        ) is True

    def test_blocks_when_hotel_missing(self):
        assert _can_approve_itinerary(
            is_round_trip=False,
            selected_flight_idx=0,
            selected_hotel_idx=None,
            selected_return_idx=None,
            selected_outbound={},
        ) is False

    def test_blocks_when_flight_missing(self):
        assert _can_approve_itinerary(
            is_round_trip=False,
            selected_flight_idx=None,
            selected_hotel_idx=0,
            selected_return_idx=None,
            selected_outbound={},
        ) is False

    def test_round_trip_requires_return_selection_when_not_embedded(self):
        assert _can_approve_itinerary(
            is_round_trip=True,
            selected_flight_idx=0,
            selected_hotel_idx=0,
            selected_return_idx=None,
            selected_outbound={"return_details_available": False},
        ) is False

    def test_round_trip_accepts_embedded_return_details(self):
        assert _can_approve_itinerary(
            is_round_trip=True,
            selected_flight_idx=0,
            selected_hotel_idx=0,
            selected_return_idx=None,
            selected_outbound={"return_details_available": True},
        ) is True


class TestIsBudgetStatusNote:
    def test_detects_redundant_within_budget_note(self):
        assert _is_budget_status_note("You're within budget with ~EUR 120 to spare.") is True

    def test_detects_redundant_over_budget_note(self):
        assert _is_budget_status_note("Estimated total exceeds your budget by EUR 50.") is True

    def test_allows_non_status_budget_guidance(self):
        assert _is_budget_status_note(
            "No flight and hotel combinations fit the selected budget. Try changing the dates."
        ) is False


class TestSessionHelpers:
    def test_start_authenticated_session_resets_trip_flow_and_sets_user(self, monkeypatch):
        calls = []

        monkeypatch.setattr(
            "presentation.streamlit_app._reset_trip_flow",
            lambda: calls.append("reset"),
        )

        import streamlit as st

        st.session_state.user_id = "default_user"
        st.session_state.authenticated = False

        _start_authenticated_session("alice")

        assert calls == ["reset"]
        assert st.session_state.user_id == "alice"
        assert st.session_state.authenticated is True

    def test_logout_clears_authentication(self, monkeypatch):
        calls = []

        monkeypatch.setattr(
            "presentation.streamlit_app._reset_trip_flow",
            lambda: calls.append("reset"),
        )

        import streamlit as st

        st.session_state.user_id = "alice"
        st.session_state.authenticated = True
        st.session_state.messages = [{"role": "user", "content": "hello"}]

        _logout()

        assert calls == ["reset"]
        assert st.session_state.user_id == "default_user"
        assert st.session_state.authenticated is False
        assert st.session_state.messages == []
