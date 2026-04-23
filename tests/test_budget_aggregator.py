"""Tests for domain/nodes/budget_aggregator.py."""

import pytest

from domain.nodes.budget_aggregator import (
    budget_aggregator,
    _destination_daily_rate,
    _filter_options_within_budget,
)
from domain.utils.dates import trip_duration_days


# ── trip_duration_days ──


class TestTripDays:
    def test_valid_dates(self):
        trip = {"departure_date": "2025-06-01", "return_date": "2025-06-08"}
        assert trip_duration_days(trip) == 7

    def test_same_day_returns_one(self):
        trip = {"departure_date": "2025-06-01", "return_date": "2025-06-01"}
        assert trip_duration_days(trip) == 1

    def test_missing_dates_returns_one(self):
        assert trip_duration_days({}) == 1
        assert trip_duration_days({"departure_date": "2025-06-01"}) == 1

    def test_invalid_format_returns_one(self):
        trip = {"departure_date": "not-a-date", "return_date": "also-not"}
        assert trip_duration_days(trip) == 1


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
        assert h == [{"total_price": 100}]

    def test_preserves_partial_results_when_only_flights_exist(self):
        flights = [{"price": 200}]
        f, h = _filter_options_within_budget(flights, [], 1000, 50)
        assert f == flights
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
            "flight_options": flights if flights is not None else [
                {"price": 300},
                {"price": 500},
            ],
            "hotel_options": hotels if hotels is not None else [
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

    def test_partial_hotel_results_are_preserved_when_flights_missing(self):
        result = budget_aggregator(self._base_state(
            budget_limit=1000,
            flights=[],
            hotels=[{"total_price": 400}],
        ))
        assert result["flight_options"] == []
        assert result["hotel_options"] == [{"total_price": 400}]
        assert "Hotel options are ready" in result["budget"]["partial_results_note"]

    def test_partial_flight_results_are_preserved_when_hotels_missing(self):
        result = budget_aggregator(self._base_state(
            budget_limit=1000,
            flights=[{"price": 300}],
            hotels=[],
        ))
        assert result["flight_options"] == [{"price": 300}]
        assert result["hotel_options"] == []
        assert "Flight options are ready" in result["budget"]["partial_results_note"]

    def test_multi_city_partial_leg_notes_are_preserved(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "EUR",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-06",
                "num_travelers": 1,
            },
            "trip_legs": [
                {
                    "leg_index": 0,
                    "origin": "Berlin",
                    "destination": "Paris",
                    "departure_date": "2025-06-01",
                    "nights": 3,
                    "needs_hotel": True,
                },
                {
                    "leg_index": 1,
                    "origin": "Paris",
                    "destination": "Berlin",
                    "departure_date": "2025-06-04",
                    "nights": 0,
                    "needs_hotel": False,
                },
            ],
            "flight_options_by_leg": [[], [{"price": 180}]],
            "hotel_options_by_leg": [[{"total_price": 420}], []],
        }

        result = budget_aggregator(state)

        assert "Some legs have only partial results" in result["budget"]["partial_results_note"]
        assert "Hotel options are ready for this leg" in result["budget"]["per_leg_breakdown"][0]["partial_results_note"]

    def test_destination_fallback_no_longer_varies_by_currency(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "JPY",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
                "num_travelers": 1,
            },
            "flight_options": [{"price": 50000}],
            "hotel_options": [{"total_price": 10000}],
        }
        result = budget_aggregator(state)
        # 1 night × default fallback daily expense
        assert result["budget"]["estimated_daily_expenses"] == 80.0

    def test_unknown_currency_uses_fallback_daily_rate(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "XYZ",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
                "num_travelers": 1,
            },
            "flight_options": [{"price": 300}],
            "hotel_options": [{"total_price": 200}],
        }
        result = budget_aggregator(state)
        # 1 night × 80.0 EUR fallback
        assert result["budget"]["estimated_daily_expenses"] == 80.0

    def test_daily_expenses_scale_by_traveler_count(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "EUR",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-04",
                "num_travelers": 2,
            },
            "flight_options": [{"price": 300}],
            "hotel_options": [{"total_price": 200}],
        }
        result = budget_aggregator(state)
        # 3 days × 80 EUR/day × 2 travelers
        assert result["budget"]["estimated_daily_expenses"] == 480.0
        assert result["budget"]["daily_expense_per_traveler"] == 80.0
        assert result["budget"]["daily_expense_days"] == 3
        assert result["budget"]["daily_expense_travelers"] == 2

    def test_flight_total_price_used_for_budget(self):
        """When flights have total_price, budget should use it instead of per-person price."""
        state = {
            "trip_request": {
                "budget_limit": 2000,
                "currency": "EUR",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-08",
            },
            "flight_options": [
                {"price": 150, "total_price": 300},  # 2 adults
            ],
            "hotel_options": [{"total_price": 700}],
        }
        result = budget_aggregator(state)
        # Flight cost in budget should be 300 (total), not 150 (per-person)
        assert result["budget"]["flight_cost"] == 300


# ── _destination_daily_rate ──


class TestDestinationDailyRate:
    def test_db_backed_destination_overrides_config(self, monkeypatch):
        monkeypatch.setattr(
            "domain.nodes.budget_aggregator.load_destination_daily_expense",
            lambda destination: (125.0, "paris"),
        )
        rate = _destination_daily_rate("Paris", "EUR")
        assert rate == 125.0

    def test_known_destination_returns_baseline_rate(self):
        rate = _destination_daily_rate("Paris", "EUR")
        assert rate == 110.0

    def test_known_destination_no_longer_scales_to_usd(self):
        rate = _destination_daily_rate("Paris, France", "USD")
        assert rate == pytest.approx(110.0)

    def test_known_destination_no_longer_scales_to_jpy(self):
        rate = _destination_daily_rate("Tokyo", "JPY")
        assert rate == pytest.approx(95.0)

    def test_expensive_destination_reykjavik(self):
        # Reykjavik EUR baseline 210; EUR trip → 210.0
        rate = _destination_daily_rate("Reykjavik", "EUR")
        assert rate == 210.0

    def test_cheap_destination_bali(self):
        # Bali EUR baseline 45; EUR trip → 45.0
        rate = _destination_daily_rate("Bali, Indonesia", "EUR")
        assert rate == 45.0

    def test_unknown_destination_falls_back_to_default_daily_expense(self):
        rate = _destination_daily_rate("Timbuktu", "EUR")
        assert rate == 80.0

    def test_empty_destination_falls_back_to_default_daily_expense(self):
        rate = _destination_daily_rate("", "JPY")
        assert rate == 80.0

    def test_destination_specific_rate_reflected_in_node_output(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "EUR",
                "destination": "Tokyo",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
                "num_travelers": 1,
            },
            "flight_options": [{"price": 50000}],
            "hotel_options": [{"total_price": 10000}],
        }
        result = budget_aggregator(state)
        # 1 night × 95 EUR destination rate × 1 traveler (since EUR baseline * Tokyo/EUR factor)
        assert result["budget"]["daily_expense_per_traveler"] == 95.0
        assert result["budget"]["daily_expense_source"] == "tokyo"

    def test_db_destination_source_reflected_in_node_output(self, monkeypatch):
        monkeypatch.setattr(
            "domain.nodes.budget_aggregator.load_destination_daily_expense",
            lambda destination: (140.0, "paris"),
        )
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "EUR",
                "destination": "Paris",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
                "num_travelers": 1,
            },
            "flight_options": [{"price": 300}],
            "hotel_options": [{"total_price": 200}],
        }
        result = budget_aggregator(state)
        assert result["budget"]["daily_expense_per_traveler"] == 140.0
        assert result["budget"]["daily_expense_source"] == "paris"

    def test_unknown_destination_source_is_default(self):
        state = {
            "trip_request": {
                "budget_limit": 0,
                "currency": "EUR",
                "destination": "Kathmandu",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-02",
                "num_travelers": 1,
            },
            "flight_options": [{"price": 300}],
            "hotel_options": [{"total_price": 200}],
        }
        result = budget_aggregator(state)
        assert result["budget"]["daily_expense_source"] == "default"

    def test_flight_without_total_price_falls_back_to_price(self):
        """Flights without total_price should fall back to price field."""
        state = {
            "trip_request": {
                "budget_limit": 2000,
                "currency": "EUR",
                "departure_date": "2025-06-01",
                "return_date": "2025-06-08",
            },
            "flight_options": [{"price": 300}],
            "hotel_options": [{"total_price": 700}],
        }
        result = budget_aggregator(state)
        assert result["budget"]["flight_cost"] == 300
