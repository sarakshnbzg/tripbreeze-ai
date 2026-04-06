"""Tests for infrastructure/apis/serpapi_client.py — parameter building."""

from unittest.mock import patch, MagicMock

import pytest

from infrastructure.apis.serpapi_client import search_flights


def _mock_google_search(expected_params_subset):
    """Helper: capture the params dict passed to GoogleSearch and return empty results."""
    captured = {}

    class FakeGoogleSearch:
        def __init__(self, params):
            captured.update(params)

        def get_dict(self):
            return {"best_flights": [], "other_flights": []}

    return FakeGoogleSearch, captured


class TestSearchFlightsParams:
    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_basic_round_trip_params(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", return_date="2025-06-08", adults=2)

        params = mock_gs_cls.call_args[0][0]
        assert params["engine"] == "google_flights"
        assert params["departure_id"] == "LHR"
        assert params["arrival_id"] == "CDG"
        assert params["outbound_date"] == "2025-06-01"
        assert params["return_date"] == "2025-06-08"
        assert params["type"] == "1"  # round trip
        assert params["adults"] == 2

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_one_way_params(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01")

        params = mock_gs_cls.call_args[0][0]
        assert params["type"] == "2"  # one way
        assert "return_date" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_stops_mapping(self, mock_gs_cls):
        """Internal stops 0/1/2 maps to SerpAPI stops 1/2/3."""
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        for internal, serpapi in [(0, 1), (1, 2), (2, 3)]:
            search_flights("London", "Paris", "2025-06-01", stops=internal)
            params = mock_gs_cls.call_args[0][0]
            assert params["stops"] == serpapi, f"stops={internal} should map to {serpapi}"

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_stops_none_not_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", stops=None)

        params = mock_gs_cls.call_args[0][0]
        assert "stops" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_max_price_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", max_price=500)

        params = mock_gs_cls.call_args[0][0]
        assert params["max_price"] == 500

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_max_price_zero_not_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", max_price=0)

        params = mock_gs_cls.call_args[0][0]
        assert "max_price" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_max_duration_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", max_duration=300)

        params = mock_gs_cls.call_args[0][0]
        assert params["max_duration"] == 300

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_bags_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", bags=2)

        params = mock_gs_cls.call_args[0][0]
        assert params["bags"] == 2

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_emissions_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", emissions=True)

        params = mock_gs_cls.call_args[0][0]
        assert params["emissions"] == 1

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_emissions_false_not_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", emissions=False)

        params = mock_gs_cls.call_args[0][0]
        assert "emissions" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_layover_duration_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", layover_duration_min=60, layover_duration_max=180)

        params = mock_gs_cls.call_args[0][0]
        assert params["layover_duration"] == "60,180"

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_layover_duration_missing_max_not_included(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", layover_duration_min=60, layover_duration_max=None)

        params = mock_gs_cls.call_args[0][0]
        assert "layover_duration" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_include_airlines(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", include_airlines=["LH", "BA"])

        params = mock_gs_cls.call_args[0][0]
        assert params["include_airlines"] == "LH,BA"
        assert "exclude_airlines" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_exclude_airlines(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", exclude_airlines=["FR"])

        params = mock_gs_cls.call_args[0][0]
        assert params["exclude_airlines"] == "FR"
        assert "include_airlines" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_include_airlines_takes_precedence_over_exclude(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", include_airlines=["LH"], exclude_airlines=["FR"])

        params = mock_gs_cls.call_args[0][0]
        assert params["include_airlines"] == "LH"
        assert "exclude_airlines" not in params

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_city_to_airport_mapping(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("Tokyo", "New York", "2025-06-01")

        params = mock_gs_cls.call_args[0][0]
        assert params["departure_id"] == "NRT"
        assert params["arrival_id"] == "JFK"

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_travel_class_mapping(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", travel_class="BUSINESS")

        params = mock_gs_cls.call_args[0][0]
        assert params["travel_class"] == "3"

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_outbound_time_window(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {"best_flights": [], "other_flights": []}

        search_flights("London", "Paris", "2025-06-01", outbound_time_window=(8, 18))

        params = mock_gs_cls.call_args[0][0]
        assert params["outbound_times"] == "8,18"

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_flight_result_normalisation(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {
            "best_flights": [
                {
                    "flights": [
                        {
                            "airline": "British Airways",
                            "departure_airport": {"id": "LHR", "time": "08:00"},
                            "arrival_airport": {"id": "CDG", "time": "10:30"},
                        }
                    ],
                    "total_duration": 150,
                    "price": 250,
                }
            ],
            "other_flights": [],
        }

        results = search_flights("London", "Paris", "2025-06-01")

        assert len(results) == 1
        flight = results[0]
        assert flight["airline"] == "British Airways"
        assert flight["stops"] == 0
        assert flight["price"] == 250
        assert flight["duration"] == "2h 30m"

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_round_trip_without_inline_return_details_is_labelled(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {
            "best_flights": [
                {
                    "flights": [
                        {
                            "airline": "British Airways",
                            "departure_airport": {"id": "LHR", "time": "2025-06-01 08:00"},
                            "arrival_airport": {"id": "CDG", "time": "2025-06-01 10:30"},
                        }
                    ],
                    "total_duration": 150,
                    "price": 250,
                    "departure_token": "token-123",
                }
            ],
            "other_flights": [],
        }

        results = search_flights(
            "London",
            "Paris",
            "2025-06-01",
            return_date="2025-06-08",
        )

        assert results[0]["departure_token"] == "token-123"
        assert results[0]["return_details_available"] is False
        assert "Return details require selecting" in results[0]["return_summary"]

    @patch("infrastructure.apis.serpapi_client.GoogleSearch")
    def test_round_trip_inline_return_details_are_normalised(self, mock_gs_cls):
        mock_gs_cls.return_value.get_dict.return_value = {
            "best_flights": [
                {
                    "flights": [
                        {
                            "airline": "British Airways",
                            "departure_airport": {"id": "LHR", "time": "2025-06-01 08:00"},
                            "arrival_airport": {"id": "CDG", "time": "2025-06-01 10:30"},
                        }
                    ],
                    "return_flights": [
                        {
                            "airline": "British Airways",
                            "departure_airport": {"id": "CDG", "time": "2025-06-08 18:00"},
                            "arrival_airport": {"id": "LHR", "time": "2025-06-08 19:30"},
                        }
                    ],
                    "total_duration": 150,
                    "price": 250,
                }
            ],
            "other_flights": [],
        }

        results = search_flights(
            "London",
            "Paris",
            "2025-06-01",
            return_date="2025-06-08",
        )

        assert results[0]["return_details_available"] is True
        assert results[0]["return_summary"] == "CDG 2025-06-08 18:00 → LHR 2025-06-08 19:30"
