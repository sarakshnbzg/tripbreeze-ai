"""Tests for domain/agents/hotel_agent.py."""

from unittest.mock import patch

from domain.agents.hotel_agent import search_hotels


class TestSearchHotelsNode:
    def _base_state(self, **trip_overrides):
        trip = {
            "destination": "Paris",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-08",
            "num_travelers": 2,
            "hotel_stars": [4, 5],
            "currency": "EUR",
        }
        trip.update(trip_overrides)
        return {"trip_request": trip}

    def test_missing_trip_request_returns_error(self):
        result = search_hotels({})
        assert result["hotel_options"] == []
        assert "error" in result

    def test_missing_destination_returns_warning(self):
        result = search_hotels(self._base_state(destination=""))
        assert result["hotel_options"] == []
        assert "Missing" in result["messages"][0]["content"]

    def test_missing_check_out_returns_warning(self):
        result = search_hotels(self._base_state(return_date="", check_out_date=""))
        assert result["hotel_options"] == []
        assert "one-way" in result["messages"][0]["content"].lower()

    def test_uses_check_out_date_when_no_return(self):
        """One-way trips should use check_out_date for hotel search."""
        captured = {}

        def fake_api_search(**kwargs):
            captured.update(kwargs)
            return []

        state = self._base_state(return_date="", check_out_date="2026-07-08")

        with patch("domain.agents.hotel_agent.api_search_hotels", side_effect=fake_api_search):
            result = search_hotels(state)

        assert captured["check_out"] == "2026-07-08"
        assert result["hotel_options"] == []

    def test_successful_search_passes_params(self):
        captured = {}

        def fake_api_search(**kwargs):
            captured.update(kwargs)
            return [{"name": "Hotel A", "total_price": 500}]

        with patch("domain.agents.hotel_agent.api_search_hotels", side_effect=fake_api_search):
            result = search_hotels(self._base_state())

        assert captured["destination"] == "Paris"
        assert captured["check_in"] == "2026-07-01"
        assert captured["check_out"] == "2026-07-08"
        assert captured["adults"] == 2
        assert captured["hotel_stars"] == [4, 5]
        assert captured["currency"] == "EUR"
        assert len(result["hotel_options"]) == 1

    def test_api_exception_returns_error_message(self):
        with patch(
            "domain.agents.hotel_agent.api_search_hotels",
            side_effect=RuntimeError("API down"),
        ):
            result = search_hotels(self._base_state())

        assert result["hotel_options"] == []
        assert "failed" in result["messages"][0]["content"].lower()

    def test_hotel_stars_int_normalised_to_list(self):
        captured = {}

        def fake_api_search(**kwargs):
            captured.update(kwargs)
            return []

        state = self._base_state(hotel_stars=4)

        with patch("domain.agents.hotel_agent.api_search_hotels", side_effect=fake_api_search):
            search_hotels(state)

        assert captured["hotel_stars"] == [4]

    def test_invalid_hotel_stars_filtered(self):
        captured = {}

        def fake_api_search(**kwargs):
            captured.update(kwargs)
            return []

        state = self._base_state(hotel_stars=[3, 99, 0])

        with patch("domain.agents.hotel_agent.api_search_hotels", side_effect=fake_api_search):
            search_hotels(state)

        assert captured["hotel_stars"] == [3]
