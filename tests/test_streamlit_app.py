"""Tests for presentation/streamlit_app.py helper functions."""

from datetime import date

from presentation.streamlit_app import (
    _can_approve_itinerary,
    _badge_pills_html,
    _flight_option_cards,
    _build_structured_fields_from_form,
    _build_token_usage_label,
    _hotel_option_cards,
    _is_budget_status_note,
    _normalise_selected_index,
    _parse_num_nights,
    _planning_progress_markdown,
    _render_option_card,
    _selection_button_label,
    _summarise_token_usage,
    _token_usage_table_markdown,
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


class TestTokenUsageTableMarkdown:
    def test_renders_single_markdown_table(self):
        table = _token_usage_table_markdown(
            [
                {
                    "search": "London (2026-04-20)",
                    "input": "1,840",
                    "output": "312",
                    "cost": "$0.0005",
                }
            ]
        )

        assert "| Search | Input | Output | Cost |" in table
        assert "|:---|---:|---:|---:|" in table
        assert "| London (2026-04-20) | 1,840 | 312 | $0.0005 |" in table
        assert table.count("\n") >= 2


class TestPlanningProgressMarkdown:
    def test_joins_updates_with_blank_lines(self):
        content = _planning_progress_markdown(["Planning your trip...", "**Searching flights...**", "Found 5 flight options."])
        assert content == "Planning your trip...\n\n**Searching flights...**\n\nFound 5 flight options."


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

    def test_flight_option_cards_build_display_data(self):
        cards = _flight_option_cards(
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
        cards = _hotel_option_cards(
            [
                {
                    "name": "Hotel Lumiere",
                    "rating": 9.1,
                    "price_per_night": 120,
                    "total_price": 360,
                }
            ],
            "EUR",
        )
        assert cards[0]["title"] == "Option 1: Hotel Lumiere"
        assert "Rating: 9.1" in cards[0]["details"][0]


class TestBuildStructuredFieldsFromForm:
    def test_ignores_untouched_defaults_when_free_text_is_present(self):
        result = _build_structured_fields_from_form(
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
            default_origin="Berlin",
            default_departure_date=date(2026, 4, 22),
            default_return_date=date(2026, 4, 29),
            default_currency="EUR",
        )

        assert result == {}

    def test_keeps_explicit_refinements_with_free_text(self):
        result = _build_structured_fields_from_form(
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
        assert _parse_num_nights("5") == 5

    def test_rejects_blank_value(self):
        assert _parse_num_nights("") is None

    def test_rejects_non_numeric_value(self):
        assert _parse_num_nights("five") is None

    def test_rejects_zero_or_negative_values(self):
        assert _parse_num_nights("0") is None
        assert _parse_num_nights("-2") is None


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
