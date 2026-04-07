"""Tests for domain/nodes/budget_aggregator.py."""

import pytest

from domain.nodes.budget_aggregator import budget_aggregator, _filter_options_within_budget, _trip_days


# ── _trip_days ──


class TestTripDays:
    def test_valid_dates(self):
        trip = {"departure_date": "2025-06-01", "return_date": "2025-06-08"}
        assert _trip_days(trip) == 7

    def test_same_day_returns_one(self):
        trip = {"departure_date": "2025-06-01", "return_date": "2025-06-01"}
        assert _trip_days(trip) == 1

    def test_missing_dates_returns_one(self):
        assert _trip_days({}) == 1
        assert _trip_days({"departure_date": "2025-06-01"}) == 1

    def test_invalid_format_returns_one(self):
        trip = {"departure_date": "not-a-date", "return_date": "also-not"}
        assert _trip_days(trip) == 1


# ── _filter_options_within_budget ──


class TestFilterOptionsWithinBudget:
    def test_no_budget_returns_all(self):
        flights = [{"price": 9999}]
        hotels = [{"total_price": 9999}]
        f, h = _filter_options_within_budget(flights, hotels, 0, 100)
        assert f == flights
        assert h == hotels

    def test_filters_expensive_flights(self):
        flights = [
            {"price": 200},
            {"price": 800},
        ]
        hotels = [{"total_price": 300}]
        # budget=600, daily=50 → flight + 300 + 50 <= 600 → flight <= 250
        f, h = _filter_options_within_budget(flights, hotels, 600, 50)
        assert len(f) == 1
        assert f[0]["price"] == 200

    def test_filters_expensive_hotels(self):
        flights = [{"price": 200}]
        hotels = [
            {"total_price": 100},
            {"total_price": 500},
        ]
        # budget=400, daily=50 → hotel + 200 + 50 <= 400 → hotel <= 150
        f, h = _filter_options_within_budget(flights, hotels, 400, 50)
        assert len(h) == 1
        assert h[0]["total_price"] == 100

    def test_no_viable_combinations(self):
        flights = [{"price": 500}]
        hotels = [{"total_price": 500}]
        # budget=100, daily=50 → nothing fits
        f, h = _filter_options_within_budget(flights, hotels, 100, 50)
        assert f == []
        assert h == []

    def test_empty_flights_or_hotels(self):
        f, h = _filter_options_within_budget([], [{"total_price": 100}], 1000, 50)
        assert f == []
        # Hotels can't pair with any flight, so also filtered out
        assert h == []


# ── budget_aggregator (node function) ──


class TestBudgetAggregatorNode:
    def _base_state(self, budget_limit=3000, flights=None, hotels=None):
        return {
            "trip_request": {
                "budget_limit": budget_limit,
                "currency": "EUR",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-08",
            },
            "flight_options": flights or [
                {"price": 300},
                {"price": 500},
            ],
            "hotel_options": hotels or [
                {"total_price": 400},
                {"total_price": 800},
            ],
        }

    def test_within_budget(self):
        result = budget_aggregator(self._base_state(budget_limit=5000))
        assert result["budget"]["within_budget"] is True
        assert "to spare" in result["budget"]["budget_notes"]

    def test_over_budget(self):
        result = budget_aggregator(self._base_state(budget_limit=500))
        # With daily expenses, nothing should fit
        assert result["budget"]["within_budget"] is False

    def test_no_budget_always_within(self):
        result = budget_aggregator(self._base_state(budget_limit=0))
        assert result["budget"]["within_budget"] is True

    def test_flights_filtered_by_budget(self):
        state = self._base_state(budget_limit=1500)
        before_count = len(state["flight_options"])
        result = budget_aggregator(state)
        assert result["budget"]["flights_before_budget_filter"] == before_count
        assert len(result["flight_options"]) <= before_count

    def test_current_step_set(self):
        result = budget_aggregator(self._base_state())
        assert result["current_step"] == "budget_done"

    def test_no_viable_combinations_message(self):
        result = budget_aggregator(self._base_state(
            budget_limit=100,
            flights=[{"price": 500}],
            hotels=[{"total_price": 500}],
        ))
        assert "No flight and hotel combinations" in result["budget"]["budget_notes"]
        assert result["budget"]["within_budget"] is False

    def test_jpy_uses_currency_specific_daily_rate(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "JPY",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
            },
            "flight_options": [{"price": 50000}],
            "hotel_options": [{"total_price": 10000}],
        }
        result = budget_aggregator(state)
        # 1 night × 12000 JPY/day
        assert result["budget"]["estimated_daily_expenses"] == 12000.0

    def test_unknown_currency_uses_fallback_daily_rate(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "XYZ",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
            },
            "flight_options": [{"price": 300}],
            "hotel_options": [{"total_price": 200}],
        }
        result = budget_aggregator(state)
        # 1 night × 80.0 EUR fallback
        assert result["budget"]["estimated_daily_expenses"] == 80.0
