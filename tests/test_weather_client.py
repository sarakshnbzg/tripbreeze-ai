"""Tests for infrastructure/apis/weather_client.py."""

from datetime import date, timedelta

import requests

from infrastructure.apis import weather_client


class DummyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "daily": {
                "time": ["2026-05-01", "2026-05-02"],
                "temperature_2m_max": [20, 21],
                "temperature_2m_min": [10, 11],
                "weather_code": [1, 999],
                "precipitation_probability_max": [30, 40],
            }
        }


class TestGeocodeDestination:
    def test_returns_coordinates_for_first_result(self, monkeypatch):
        monkeypatch.setattr(
            weather_client,
            "geocode_place",
            lambda destination: type(
                "Place",
                (),
                {"latitude": 48.8566, "longitude": 2.3522, "name": "Paris"},
            )(),
        )

        result = weather_client.geocode_destination("Paris")

        assert result is not None
        assert result.latitude == 48.8566
        assert result.longitude == 2.3522
        assert result.name == "Paris"

    def test_returns_none_when_no_results(self, monkeypatch):
        monkeypatch.setattr(weather_client, "geocode_place", lambda destination: None)

        assert weather_client.geocode_destination("Nowhere") is None


class TestFetchForecast:
    def test_maps_daily_payload_to_day_weather(self, monkeypatch):
        coords = weather_client.Coordinates(48.8566, 2.3522, "Paris")

        monkeypatch.setattr(
            weather_client.requests,
            "get",
            lambda *args, **kwargs: DummyResponse(),
        )

        result = weather_client._fetch_forecast(coords, "2026-05-01", "2026-05-02")

        assert len(result) == 2
        assert result[0].condition == "Mainly clear"
        assert result[1].condition == "Unknown"
        assert result[0].is_historical is False

    def test_returns_empty_list_on_request_exception(self, monkeypatch):
        coords = weather_client.Coordinates(48.8566, 2.3522, "Paris")

        def fake_get(*args, **kwargs):
            raise requests.RequestException("timeout")

        monkeypatch.setattr(weather_client.requests, "get", fake_get)

        assert weather_client._fetch_forecast(coords, "2026-05-01", "2026-05-02") == []


class TestFetchWeatherForTrip:
    def test_splits_between_forecast_and_historical_ranges(self, monkeypatch):
        forecast_date = (date.today() + timedelta(days=2)).isoformat()
        historical_date = (date.today() + timedelta(days=25)).isoformat()
        coords = weather_client.Coordinates(48.8566, 2.3522, "Paris")
        calls = {}

        monkeypatch.setattr(weather_client, "geocode_destination", lambda destination: coords)

        def fake_forecast(passed_coords, start_date, end_date):
            calls["forecast"] = (passed_coords, start_date, end_date)
            return [
                weather_client.DayWeather(
                    date=forecast_date,
                    temp_min=10,
                    temp_max=20,
                    condition="Clear sky",
                    precipitation_chance=10,
                    is_historical=False,
                )
            ]

        def fake_historical(passed_coords, start_date, end_date):
            calls["historical"] = (passed_coords, start_date, end_date)
            return [
                weather_client.DayWeather(
                    date=historical_date,
                    temp_min=8,
                    temp_max=18,
                    condition="Partly cloudy (typical)",
                    precipitation_chance=20,
                    is_historical=True,
                )
            ]

        monkeypatch.setattr(weather_client, "_fetch_forecast", fake_forecast)
        monkeypatch.setattr(weather_client, "_fetch_historical", fake_historical)

        result = weather_client.fetch_weather_for_trip(
            "Paris", [forecast_date, historical_date]
        )

        assert set(result) == {forecast_date, historical_date}
        assert calls["forecast"][1:] == (forecast_date, forecast_date)
        assert calls["historical"][1:] == (historical_date, historical_date)
        assert result[historical_date].is_historical is True

    def test_ignores_invalid_trip_dates(self, monkeypatch):
        forecast_date = (date.today() + timedelta(days=2)).isoformat()
        coords = weather_client.Coordinates(48.8566, 2.3522, "Paris")

        monkeypatch.setattr(weather_client, "geocode_destination", lambda destination: coords)
        monkeypatch.setattr(
            weather_client,
            "_fetch_forecast",
            lambda *args: [
                weather_client.DayWeather(
                    date=forecast_date,
                    temp_min=10,
                    temp_max=20,
                    condition="Clear sky",
                    precipitation_chance=10,
                    is_historical=False,
                )
            ],
        )
        monkeypatch.setattr(weather_client, "_fetch_historical", lambda *args: [])

        result = weather_client.fetch_weather_for_trip(
            "Paris", ["not-a-date", forecast_date]
        )

        assert set(result) == {forecast_date}

    def test_returns_empty_dict_when_geocoding_fails(self, monkeypatch):
        monkeypatch.setattr(weather_client, "geocode_destination", lambda destination: None)

        assert weather_client.fetch_weather_for_trip("Paris", ["2026-05-01"]) == {}
