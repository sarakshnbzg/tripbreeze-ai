"""Tests for domain/nodes/trip_intake.py."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from domain.nodes.trip_intake import (
    _apply_free_text_trip_fallbacks,
    _classify_domain,
    _extract_explicit_departure_date,
    _extract_trip_duration_days,
    _query_mentions_one_way,
    _normalise_hotel_stars,
    _normalise_trip_data,
    _parse_preferences,
    _validate_date,
    trip_intake,
)

# Future dates used across test fixtures
_DEPARTURE = str(date.today() + timedelta(days=30))
_RETURN = str(date.today() + timedelta(days=37))


# ── _normalise_hotel_stars ──


class TestNormaliseHotelStars:
    def test_empty_list_falls_back_to_profile(self):
        assert _normalise_hotel_stars([], {"preferred_hotel_stars": [3, 4]}) == [3, 4]

    def test_none_falls_back_to_profile(self):
        assert _normalise_hotel_stars(None, {"preferred_hotel_stars": [5]}) == [5]

    def test_empty_string_falls_back_to_profile(self):
        assert _normalise_hotel_stars("", {"preferred_hotel_stars": [4]}) == [4]

    def test_explicit_list_ignores_profile(self):
        assert _normalise_hotel_stars([3, 5], {"preferred_hotel_stars": [4]}) == [3, 5]

    def test_single_int_wrapped_in_list(self):
        assert _normalise_hotel_stars(4, {}) == [4]

    def test_out_of_range_values_filtered(self):
        assert _normalise_hotel_stars([0, 3, 6, -1], {}) == [3]

    def test_duplicates_removed(self):
        assert _normalise_hotel_stars([3, 3, 4, 4], {}) == [3, 4]

    def test_sorted_output(self):
        assert _normalise_hotel_stars([5, 2, 3], {}) == [2, 3, 5]

    def test_non_int_values_skipped(self):
        assert _normalise_hotel_stars(["abc", 3, None], {}) == [3]

    def test_empty_profile_returns_empty(self):
        assert _normalise_hotel_stars([], {}) == []


# ── _validate_date ──


class TestValidateDate:
    def test_empty_returns_empty(self):
        assert _validate_date("", "Test") == ""

    def test_valid_future_date(self):
        assert _validate_date(_DEPARTURE, "Test") == _DEPARTURE

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="not a valid date"):
            _validate_date("not-a-date", "Test")

    def test_past_date_raises(self):
        yesterday = str(date.today() - timedelta(days=1))
        with pytest.raises(ValueError, match="in the past"):
            _validate_date(yesterday, "Test")

    def test_today_is_accepted(self):
        today = str(date.today())
        assert _validate_date(today, "Test") == today


# ── _normalise_trip_data ──


class TestFreeTextTripFallbacks:
    def test_extracts_explicit_departure_date(self):
        assert _extract_explicit_departure_date("I want to leave on 20th of April") == "2026-04-20"

    def test_extracts_trip_duration_days(self):
        assert _extract_trip_duration_days("I want to stay for 2 days") == 2

    def test_extracts_worded_trip_duration_days(self):
        assert _extract_trip_duration_days("I want a one day trip to London") == 1
        assert _extract_trip_duration_days("Plan a one-day trip from Berlin to London") == 1

    def test_extracts_day_trip_phrase(self):
        assert _extract_trip_duration_days("Plan a day trip from Berlin to London") == 1

    def test_detects_one_way_phrase(self):
        assert _query_mentions_one_way("I want a one way flight to Barcelona") is True
        assert _query_mentions_one_way("I want a one-way flight to Barcelona") is True

    def test_duration_and_date_override_missing_or_incorrect_llm_dates(self):
        raw = {
            "origin": "Berlin",
            "destination": "London",
            "departure_date": "2026-04-22",
            "return_date": "2026-04-29",
        }

        result = _apply_free_text_trip_fallbacks(
            raw,
            "I want to fly from Berlin to London for 2 day from 20th of April. Give me a plan.",
            {},
        )

        assert result["departure_date"] == "2026-04-20"
        assert result["return_date"] == "2026-04-22"
        assert result["check_out_date"] == "2026-04-22"

    def test_structured_dates_are_not_overridden(self):
        raw = {
            "departure_date": "2026-04-25",
            "return_date": "2026-04-28",
        }

        result = _apply_free_text_trip_fallbacks(
            raw,
            "I want to fly from Berlin to London for 2 day from 20th of April. Give me a plan.",
            {"departure_date": "2026-04-25", "return_date": "2026-04-28"},
        )

        assert result["departure_date"] == "2026-04-25"
        assert result["return_date"] == "2026-04-28"

    def test_one_way_duration_sets_check_out_not_return_date(self):
        raw = {
            "origin": "Berlin",
            "destination": "Barcelona",
            "departure_date": "2026-04-22",
            "return_date": "2026-04-29",
        }

        result = _apply_free_text_trip_fallbacks(
            raw,
            "I want to fly from Berlin to Barcelona on the 19th of April. One way for 2 nights.",
            {},
        )

        assert result["departure_date"] == "2026-04-19"
        assert result["return_date"] == ""
        assert result["check_out_date"] == "2026-04-21"


class TestClassifyDomain:
    def test_empty_query_defaults_to_in_domain(self):
        result, usage = _classify_domain(None, "", model="gpt-4o-mini")
        assert result == {"in_domain": True, "reason": ""}
        assert usage is None

    @patch("domain.nodes.trip_intake.extract_token_usage")
    @patch("domain.nodes.trip_intake.invoke_with_retry")
    def test_llm_domain_tool_result_returned(self, mock_invoke_with_retry, mock_extract_token_usage):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [{"args": {"in_domain": False, "reason": "Unrelated to travel"}}]
        mock_llm.bind_tools.return_value = MagicMock()
        mock_invoke_with_retry.return_value = mock_response
        mock_extract_token_usage.return_value = {"node": "domain_guardrail", "model": "gpt-4o-mini"}

        result, usage = _classify_domain(
            mock_llm,
            "Explain quantum computing.",
            model="gpt-4o-mini",
        )

        assert result == {"in_domain": False, "reason": "Unrelated to travel"}
        assert usage == {"node": "domain_guardrail", "model": "gpt-4o-mini"}

    @patch("domain.nodes.trip_intake.extract_token_usage")
    @patch("domain.nodes.trip_intake.invoke_with_retry")
    def test_missing_tool_call_falls_back_to_in_domain(self, mock_invoke_with_retry, mock_extract_token_usage):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_llm.bind_tools.return_value = MagicMock()
        mock_invoke_with_retry.return_value = mock_response
        mock_extract_token_usage.return_value = {"node": "domain_guardrail", "model": "gpt-4o-mini"}

        result, usage = _classify_domain(
            mock_llm,
            "Plan a trip to Rome.",
            model="gpt-4o-mini",
        )

        assert result == {"in_domain": True, "reason": ""}
        assert usage == {"node": "domain_guardrail", "model": "gpt-4o-mini"}


class TestNormaliseTripData:
    def _base_raw(self, **overrides):
        data = {
            "origin": "London",
            "destination": "Paris",
            "departure_date": _DEPARTURE,
            "return_date": _RETURN,
            "num_travelers": 2,
            "budget_limit": 3000,
            "currency": "eur",
            "travel_class": "economy",
            "hotel_stars": [],
            "preferences": "direct flights only",
        }
        data.update(overrides)
        return data

    def test_basic_normalisation(self):
        result = _normalise_trip_data(self._base_raw(), {})
        assert result["origin"] == "London"
        assert result["destination"] == "Paris"
        assert result["currency"] == "EUR"
        assert result["travel_class"] == "ECONOMY"
        assert result["num_travelers"] == 2
        assert result["budget_limit"] == 3000.0

    def test_origin_falls_back_to_profile_home_city(self):
        result = _normalise_trip_data(self._base_raw(origin=""), {"home_city": "Berlin"})
        assert result["origin"] == "Berlin"

    def test_travel_class_falls_back_to_profile(self):
        result = _normalise_trip_data(
            self._base_raw(travel_class=""), {"travel_class": "BUSINESS"}
        )
        assert result["travel_class"] == "BUSINESS"

    def test_num_travelers_minimum_is_one(self):
        result = _normalise_trip_data(self._base_raw(num_travelers=0), {})
        assert result["num_travelers"] == 1

    def test_stops_valid_values(self):
        for stops_val in (0, 1, 2):
            result = _normalise_trip_data(self._base_raw(stops=stops_val), {})
            assert result["stops"] == stops_val

    def test_stops_out_of_range_becomes_none(self):
        result = _normalise_trip_data(self._base_raw(stops=5), {})
        assert result["stops"] is None

    def test_stops_none_stays_none(self):
        result = _normalise_trip_data(self._base_raw(stops=None), {})
        assert result["stops"] is None

    def test_stops_invalid_type_becomes_none(self):
        result = _normalise_trip_data(self._base_raw(stops="abc"), {})
        assert result["stops"] is None

    def test_max_flight_price_normalised(self):
        result = _normalise_trip_data(self._base_raw(max_flight_price=500), {})
        assert result["max_flight_price"] == 500.0

    def test_max_flight_price_negative_becomes_zero(self):
        result = _normalise_trip_data(self._base_raw(max_flight_price=-100), {})
        assert result["max_flight_price"] == 0

    def test_max_duration_normalised(self):
        result = _normalise_trip_data(self._base_raw(max_duration=300), {})
        assert result["max_duration"] == 300

    def test_bags_normalised(self):
        result = _normalise_trip_data(self._base_raw(bags=2), {})
        assert result["bags"] == 2

    def test_emissions_normalised(self):
        result = _normalise_trip_data(self._base_raw(emissions=True), {})
        assert result["emissions"] is True

    def test_emissions_default_false(self):
        result = _normalise_trip_data(self._base_raw(), {})
        assert result["emissions"] is False

    def test_airline_lists_default_empty(self):
        result = _normalise_trip_data(self._base_raw(), {})
        assert result["include_airlines"] == []
        assert result["exclude_airlines"] == []

    def test_airline_lists_preserved(self):
        result = _normalise_trip_data(
            self._base_raw(include_airlines=["LH"], exclude_airlines=["FR"]), {}
        )
        assert result["include_airlines"] == ["LH"]
        assert result["exclude_airlines"] == ["FR"]

    def test_hotel_stars_user_specified_flag(self):
        result = _normalise_trip_data(self._base_raw(hotel_stars=[4, 5]), {})
        assert result["hotel_stars_user_specified"] is True

        result = _normalise_trip_data(self._base_raw(hotel_stars=[]), {})
        assert result["hotel_stars_user_specified"] is False

    def test_one_way_without_check_out_date_raises(self):
        with pytest.raises(ValueError, match="One-way trips require"):
            _normalise_trip_data(
                self._base_raw(return_date="", check_out_date=""),
                {},
            )


# ── _parse_preferences ──


class TestParsePreferences:
    def test_empty_preferences_returns_empty(self):
        assert _parse_preferences(None, "", model="gpt-4o-mini") == ({}, None)
        assert _parse_preferences(None, "   ", model="gpt-4o-mini") == ({}, None)

    @patch("domain.nodes.trip_intake.extract_token_usage")
    @patch("domain.nodes.trip_intake.invoke_with_retry")
    def test_llm_tool_call_result_returned(self, mock_invoke_with_retry, mock_extract_token_usage):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"args": {"stops": 0, "max_flight_price": 400}}
        ]
        mock_bound = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound
        mock_invoke_with_retry.return_value = mock_response
        mock_extract_token_usage.return_value = {"node": "trip_intake", "model": "gpt-4o-mini"}

        parsed, usage = _parse_preferences(
            mock_llm,
            "direct flights, under 400 euros",
            model="gpt-4o-mini",
        )

        assert parsed == {"stops": 0, "max_flight_price": 400}
        assert usage == {"node": "trip_intake", "model": "gpt-4o-mini"}

    @patch("domain.nodes.trip_intake.extract_token_usage")
    @patch("domain.nodes.trip_intake.invoke_with_retry")
    def test_no_tool_calls_returns_empty(self, mock_invoke_with_retry, mock_extract_token_usage):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_bound = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound
        mock_invoke_with_retry.return_value = mock_response
        mock_extract_token_usage.return_value = {"node": "trip_intake", "model": "gpt-4o-mini"}

        parsed, usage = _parse_preferences(mock_llm, "some preferences", model="gpt-4o-mini")
        assert parsed == {}
        assert usage == {"node": "trip_intake", "model": "gpt-4o-mini"}


# ── trip_intake (node function) ──


class TestTripIntakeNode:
    def _base_state(self, **overrides):
        state = {
            "user_profile": {},
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "structured_fields": {
                "origin": "London",
                "destination": "Paris",
                "departure_date": _DEPARTURE,
                "return_date": _RETURN,
                "num_travelers": 2,
                "budget_limit": 3000,
                "currency": "EUR",
                "preferences": "",
            },
        }
        state.update(overrides)
        return state

    def test_structured_fields_pass_through_without_llm(self):
        state = self._base_state()
        result = trip_intake(state)

        assert result["current_step"] == "intake_complete"
        trip = result["trip_request"]
        assert trip["origin"] == "London"
        assert trip["destination"] == "Paris"
        assert trip["num_travelers"] == 2

    def test_preferences_triggers_llm_parsing(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [{"args": {"stops": 0}}]
        mock_bound = MagicMock()
        mock_bound.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_bound

        state = self._base_state()
        state["structured_fields"]["preferences"] = "direct flights only"

        with patch("domain.nodes.trip_intake.create_chat_model", return_value=mock_llm):
            result = trip_intake(state)

        assert result["trip_request"]["stops"] == 0

    def test_no_preferences_skips_llm(self):
        state = self._base_state()

        with patch("domain.nodes.trip_intake.create_chat_model") as mock_create:
            result = trip_intake(state)
            mock_create.assert_not_called()

        assert result["current_step"] == "intake_complete"

    def test_empty_structured_fields_returns_defaults(self):
        state = self._base_state(structured_fields={})
        result = trip_intake(state)

        trip = result["trip_request"]
        assert trip["origin"] == ""
        assert trip["destination"] == ""
        assert trip["num_travelers"] == 1

    def test_confirmation_message_included(self):
        state = self._base_state()
        result = trip_intake(state)

        messages = result["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert "London" in messages[0]["content"]
        assert "Paris" in messages[0]["content"]

    def test_confirmation_message_uses_trip_currency(self):
        state = self._base_state()
        state["structured_fields"]["currency"] = "USD"
        state["structured_fields"]["budget_limit"] = 1200

        result = trip_intake(state)

        assert "$1,200" in result["messages"][0]["content"]

    def test_validation_error_returns_friendly_message(self):
        state = self._base_state()
        state["structured_fields"]["departure_date"] = _RETURN
        state["structured_fields"]["return_date"] = _DEPARTURE  # return before departure

        result = trip_intake(state)

        assert result["current_step"] == "intake_error"
        assert "messages" in result
        assert "couldn't process" in result["messages"][0]["content"].lower()

    def test_one_way_without_stay_length_returns_validation_message(self):
        state = self._base_state()
        state["structured_fields"]["return_date"] = ""
        state["structured_fields"]["check_out_date"] = ""

        result = trip_intake(state)

        assert result["current_step"] == "intake_error"
        assert "number of nights or a check-out date" in result["messages"][0]["content"].lower()

    def test_validation_error_does_not_expose_exception_type(self):
        state = self._base_state()
        state["structured_fields"]["departure_date"] = "not-a-date"

        result = trip_intake(state)

        assert result["current_step"] == "intake_error"
        assert "messages" in result
        # Should have a user-facing message, not a raw traceback
        assert result["messages"][0]["role"] == "assistant"

    def test_out_of_domain_free_text_returns_guardrail_message(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [{"args": {"in_domain": False, "reason": "General knowledge request"}}]
        mock_llm.bind_tools.return_value = MagicMock()

        state = self._base_state(
            structured_fields={},
            free_text_query="Explain quantum computing in simple terms.",
        )

        with patch("domain.nodes.trip_intake.create_chat_model", return_value=mock_llm):
            with patch("domain.nodes.trip_intake.invoke_with_retry", return_value=mock_response):
                with patch("domain.nodes.trip_intake.extract_token_usage", return_value=None):
                    result = trip_intake(state)

        assert result["current_step"] == "out_of_domain"
        assert "travel planning only" in result["messages"][0]["content"].lower()

    def test_structured_trip_signal_skips_domain_guardrail(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"args": {"origin": "Berlin", "destination": "Rome", "departure_date": _DEPARTURE}}
        ]
        mock_llm.bind_tools.return_value = MagicMock()

        state = self._base_state(
            structured_fields={"destination": "Rome"},
            free_text_query="Tell me something interesting.",
        )

        with patch("domain.nodes.trip_intake.create_chat_model", return_value=mock_llm):
            with patch("domain.nodes.trip_intake.invoke_with_retry", return_value=mock_response) as mock_invoke:
                with patch("domain.nodes.trip_intake.extract_token_usage", return_value=None):
                    trip_intake(state)

        assert mock_invoke.call_count == 1

    def test_free_text_duration_and_explicit_date_fix_llm_misread(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {
                "args": {
                    "origin": "Berlin",
                    "destination": "London",
                    "departure_date": "2026-04-22",
                    "return_date": "2026-04-29",
                }
            }
        ]
        mock_bound = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound

        state = self._base_state(
            structured_fields={},
            free_text_query="I want to fly from Berlin to London for 2 day from 20th of April. Give me a plan.",
        )

        with patch("domain.nodes.trip_intake.create_chat_model", return_value=mock_llm):
            with patch("domain.nodes.trip_intake.invoke_with_retry", return_value=mock_response):
                with patch("domain.nodes.trip_intake.extract_token_usage", return_value=None):
                    result = trip_intake(state)

        trip = result["trip_request"]
        assert trip["departure_date"] == "2026-04-20"
        assert trip["return_date"] == "2026-04-22"
        assert trip["check_out_date"] == "2026-04-22"

    def test_free_text_one_way_duration_does_not_create_round_trip(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {
                "args": {
                    "origin": "Berlin",
                    "destination": "Barcelona",
                    "departure_date": "2026-04-22",
                    "return_date": "2026-04-29",
                }
            }
        ]
        mock_llm.bind_tools.return_value = MagicMock()

        state = self._base_state(
            structured_fields={},
            free_text_query="I want to fly from Berlin to Barcelona on the 19th of April. One way for 2 nights.",
        )

        with patch("domain.nodes.trip_intake.create_chat_model", return_value=mock_llm):
            with patch("domain.nodes.trip_intake.invoke_with_retry", return_value=mock_response):
                with patch("domain.nodes.trip_intake.extract_token_usage", return_value=None):
                    result = trip_intake(state)

        trip = result["trip_request"]
        assert trip["departure_date"] == "2026-04-19"
        assert trip["return_date"] == ""
        assert trip["check_out_date"] == "2026-04-21"
        assert "(one-way)" in result["messages"][0]["content"]
