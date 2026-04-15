"""Tests for domain/agents/flight_agent.py."""

from unittest.mock import patch

import pytest

from domain.agents.flight_agent import (
    _normalise_time_window,
    _rank_flights_by_preferred_airlines,
    _rank_flights_by_preferences,
    search_flights,
)


# ── _normalise_time_window ──


class TestNormaliseTimeWindow:
    def test_valid_window(self):
        assert _normalise_time_window([8, 20]) == (8, 20)

    def test_none_returns_none(self):
        assert _normalise_time_window(None) is None

    def test_not_a_list_returns_none(self):
        assert _normalise_time_window("8,20") is None

    def test_wrong_length_returns_none(self):
        assert _normalise_time_window([8]) is None
        assert _normalise_time_window([8, 12, 20]) is None

    def test_out_of_range_returns_none(self):
        assert _normalise_time_window([-1, 20]) is None
        assert _normalise_time_window([8, 25]) is None

    def test_start_after_end_returns_none(self):
        assert _normalise_time_window([20, 8]) is None

    def test_same_start_end_valid(self):
        assert _normalise_time_window([12, 12]) == (12, 12)


# ── _rank_flights_by_preferred_airlines ──


class TestRankFlightsByPreferredAirlines:
    def test_preferred_airlines_ranked_first(self):
        flights = [
            {"airline": "Ryanair", "price": 100},
            {"airline": "Lufthansa", "price": 300},
            {"airline": "EasyJet", "price": 150},
        ]
        ranked = _rank_flights_by_preferred_airlines(flights, ["Lufthansa"])
        assert ranked[0]["airline"] == "Lufthansa"

    def test_empty_preferred_returns_unchanged(self):
        flights = [{"airline": "A"}, {"airline": "B"}]
        assert _rank_flights_by_preferred_airlines(flights, []) == flights

    def test_no_match_returns_unchanged(self):
        flights = [{"airline": "A"}, {"airline": "B"}]
        result = _rank_flights_by_preferred_airlines(flights, ["C"])
        assert result == flights

    def test_partial_name_match(self):
        flights = [
            {"airline": "EasyJet", "price": 100},
            {"airline": "British Airways", "price": 400},
        ]
        ranked = _rank_flights_by_preferred_airlines(flights, ["british"])
        assert ranked[0]["airline"] == "British Airways"


class TestRankFlightsByPreferences:
    def test_scores_preferred_airline_and_time_window_above_cheaper_option(self):
        flights = [
            {"airline": "Budget Air", "price": 120, "duration": "2h 30m", "stops": 1, "departure_time": "06:00"},
            {"airline": "Lufthansa", "price": 180, "duration": "2h 10m", "stops": 0, "departure_time": "09:00"},
        ]
        ranked = _rank_flights_by_preferences(
            flights,
            {"max_flight_price": 250},
            {"preferred_airlines": ["Lufthansa"], "preferred_outbound_time_window": [8, 12]},
        )
        assert ranked[0]["airline"] == "Lufthansa"
        assert "matches preferred airline" in ranked[0]["preference_reasons"]
        assert "fits preferred departure window" in ranked[0]["preference_reasons"]

    def test_adds_preference_metadata(self):
        ranked = _rank_flights_by_preferences(
            [{"airline": "Lufthansa", "price": 180, "duration": "2h", "stops": 0, "departure_time": "09:00"}],
            {"max_flight_price": 250},
            {"preferred_airlines": ["Lufthansa"], "preferred_outbound_time_window": [8, 12]},
        )
        assert ranked[0]["preference_score"] > 0
        assert isinstance(ranked[0]["preference_reasons"], list)


# ── search_flights (node function) ──


class TestSearchFlightsNode:
    def _base_state(self, **trip_overrides):
        trip = {
            "origin": "London",
            "destination": "Paris",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
            "num_travelers": 2,
            "travel_class": "ECONOMY",
            "currency": "EUR",
            "budget_limit": 0,
            "max_flight_price": 0,
            "stops": None,
            "max_duration": 0,
            "bags": 0,
            "emissions": False,
            "layover_duration_min": 0,
            "layover_duration_max": 0,
            "include_airlines": [],
            "exclude_airlines": [],
        }
        trip.update(trip_overrides)
        return {"trip_request": trip, "user_profile": {}}

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_max_price_from_explicit_max_flight_price(self, mock_api):
        mock_api.return_value = []
        search_flights(self._base_state(max_flight_price=400))
        _, kwargs = mock_api.call_args
        assert kwargs["max_price"] == 400

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_max_price_derived_from_budget(self, mock_api):
        mock_api.return_value = []
        # budget 4000, 2 travelers → 4000 / 2 * 0.5 = 1000
        search_flights(self._base_state(budget_limit=4000, num_travelers=2))
        _, kwargs = mock_api.call_args
        assert kwargs["max_price"] == 1000

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_explicit_max_flight_price_takes_precedence_over_budget(self, mock_api):
        mock_api.return_value = []
        search_flights(self._base_state(max_flight_price=300, budget_limit=4000, num_travelers=2))
        _, kwargs = mock_api.call_args
        assert kwargs["max_price"] == 300

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_no_budget_no_max_price(self, mock_api):
        mock_api.return_value = []
        search_flights(self._base_state(budget_limit=0, max_flight_price=0))
        _, kwargs = mock_api.call_args
        assert kwargs["max_price"] is None

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_stops_passed_through(self, mock_api):
        mock_api.return_value = []
        search_flights(self._base_state(stops=0))
        _, kwargs = mock_api.call_args
        assert kwargs["stops"] == 0

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_new_filter_params_passed_through(self, mock_api):
        mock_api.return_value = []
        search_flights(self._base_state(
            max_duration=300,
            bags=2,
            emissions=True,
            layover_duration_min=60,
            layover_duration_max=180,
            include_airlines=["LH"],
        ))
        _, kwargs = mock_api.call_args
        assert kwargs["max_duration"] == 300
        assert kwargs["bags"] == 2
        assert kwargs["emissions"] is True
        assert kwargs["layover_duration_min"] == 60
        assert kwargs["layover_duration_max"] == 180
        assert kwargs["include_airlines"] == ["LH"]

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_missing_required_fields_returns_error(self, mock_api):
        state = {"trip_request": {"origin": "", "destination": "", "departure_date": ""}, "user_profile": {}}
        result = search_flights(state)
        assert result["flight_options"] == []
        mock_api.assert_not_called()

    @patch("domain.agents.flight_agent.api_search_flights")
    def test_missing_trip_request_returns_error(self, mock_api):
        result = search_flights({"user_profile": {}})
        assert result["flight_options"] == []
        assert "error" in result
