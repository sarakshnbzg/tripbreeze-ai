"""Tests for infrastructure/apis/ground_transport_client.py."""

from infrastructure.apis.ground_transport_client import (
    _estimate_distance_km,
    _format_duration,
    _google_maps_transit_url,
    search_ground_transport,
)


class TestGroundTransportHelpers:
    def test_google_maps_url_contains_origin_and_destination(self):
        url = _google_maps_transit_url("Berlin", "Paris", "2026-06-01")

        assert "origin=Berlin" in url
        assert "destination=Paris" in url
        assert "travelmode=transit" in url

    def test_estimate_distance_is_deterministic(self):
        assert _estimate_distance_km("Berlin", "Paris") == _estimate_distance_km("Berlin", "Paris")

    def test_format_duration(self):
        assert _format_duration(125) == "2h 5m"


class TestSearchGroundTransport:
    def test_returns_empty_for_missing_inputs(self):
        assert search_ground_transport("", "Paris", "2026-06-01") == []
        assert search_ground_transport("Berlin", "", "2026-06-01") == []
        assert search_ground_transport("Berlin", "Paris", "") == []

    def test_returns_empty_for_invalid_date(self):
        assert search_ground_transport("Berlin", "Paris", "not-a-date") == []

    def test_returns_mock_options_with_total_price_scaling(self):
        options = search_ground_transport(
            "Berlin",
            "Paris",
            "2026-06-01",
            adults=2,
            currency="EUR",
        )

        assert options
        assert all(option["currency"] == "EUR" for option in options)
        assert all(option["total_price"] >= option["price"] for option in options)
        assert all("booking_url" in option for option in options)
