"""Tests for domain/nodes/trip_intake.py."""

from unittest.mock import MagicMock, patch

import pytest

from domain.nodes.trip_intake import (
    _normalise_hotel_stars,
    _normalise_trip_data,
    _parse_preferences,
    trip_intake,
)


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


# ── _normalise_trip_data ──


class TestNormaliseTripData:
    def _base_raw(self, **overrides):
        data = {
            "origin": "London",
            "destination": "Paris",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
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


# ── _parse_preferences ──


class TestParsePreferences:
    def test_empty_preferences_returns_empty(self):
        assert _parse_preferences(None, "") == {}
        assert _parse_preferences(None, "   ") == {}

    def test_llm_tool_call_result_returned(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"args": {"stops": 0, "max_flight_price": 400}}
        ]
        mock_bound = MagicMock()
        mock_bound.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_bound

        result = _parse_preferences(mock_llm, "direct flights, under 400 euros")
        assert result == {"stops": 0, "max_flight_price": 400}

    def test_no_tool_calls_returns_empty(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_bound = MagicMock()
        mock_bound.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_bound

        result = _parse_preferences(mock_llm, "some preferences")
        assert result == {}


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
                "departure_date": "2025-06-01",
                "return_date": "2025-06-08",
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
