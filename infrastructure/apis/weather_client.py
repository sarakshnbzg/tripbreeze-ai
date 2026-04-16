"""Open-Meteo weather client — provides weather forecasts and historical climate data.

Uses the shared Open-Meteo geocoder plus Open-Meteo's free weather APIs for:
- Forecasts: up to 16 days ahead
- Historical: same dates from previous year for trips beyond forecast range
"""

from datetime import date, timedelta
from typing import NamedTuple

import requests

from infrastructure.apis.geocoding_client import geocode_place
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"

# WMO weather codes to human-readable descriptions
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class DayWeather(NamedTuple):
    """Weather data for a single day."""

    date: str
    temp_min: float
    temp_max: float
    condition: str
    precipitation_chance: int
    is_historical: bool  # True if based on previous year's data


class Coordinates(NamedTuple):
    """Geographic coordinates."""

    latitude: float
    longitude: float
    name: str


def geocode_destination(destination: str) -> Coordinates | None:
    """Convert a destination name to coordinates using the shared geocoder."""
    place = geocode_place(destination)
    if place is None:
        return None
    return Coordinates(latitude=place.latitude, longitude=place.longitude, name=place.name)


def _fetch_forecast(
    coords: Coordinates, start_date: str, end_date: str
) -> list[DayWeather]:
    """Fetch weather forecast for dates within the 16-day forecast window."""
    try:
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": coords.latitude,
                "longitude": coords.longitude,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "auto",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        temp_maxs = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        weather_codes = daily.get("weather_code", [])
        precip_chances = daily.get("precipitation_probability_max", [])

        results = []
        for i, d in enumerate(dates):
            code = weather_codes[i] if i < len(weather_codes) else 0
            results.append(
                DayWeather(
                    date=d,
                    temp_min=temp_mins[i] if i < len(temp_mins) else 0,
                    temp_max=temp_maxs[i] if i < len(temp_maxs) else 0,
                    condition=WMO_CODES.get(code, "Unknown"),
                    precipitation_chance=precip_chances[i] if i < len(precip_chances) else 0,
                    is_historical=False,
                )
            )
        return results

    except requests.RequestException as exc:
        logger.error("Forecast request failed: %s", exc)
        return []


def _fetch_historical(
    coords: Coordinates, start_date: str, end_date: str
) -> list[DayWeather]:
    """Fetch historical weather for same dates from previous year."""
    # Shift dates back by one year
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    hist_start = (start - timedelta(days=365)).isoformat()
    hist_end = (end - timedelta(days=365)).isoformat()

    try:
        response = requests.get(
            HISTORICAL_URL,
            params={
                "latitude": coords.latitude,
                "longitude": coords.longitude,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
                "start_date": hist_start,
                "end_date": hist_end,
                "timezone": "auto",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        daily = data.get("daily", {})
        hist_dates = daily.get("time", [])
        temp_maxs = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        weather_codes = daily.get("weather_code", [])
        precip_sums = daily.get("precipitation_sum", [])

        # Map historical dates back to the requested dates
        results = []
        target_date = start
        for i, _ in enumerate(hist_dates):
            if target_date > end:
                break
            code = weather_codes[i] if i < len(weather_codes) else 0
            # Estimate precipitation chance from historical precipitation amount
            precip = precip_sums[i] if i < len(precip_sums) else 0
            precip_chance = min(100, int((precip or 0) * 20))  # rough estimate

            results.append(
                DayWeather(
                    date=target_date.isoformat(),
                    temp_min=temp_mins[i] if i < len(temp_mins) else 0,
                    temp_max=temp_maxs[i] if i < len(temp_maxs) else 0,
                    condition=WMO_CODES.get(code, "Unknown") + " (typical)",
                    precipitation_chance=precip_chance,
                    is_historical=True,
                )
            )
            target_date += timedelta(days=1)

        return results

    except requests.RequestException as exc:
        logger.error("Historical weather request failed: %s", exc)
        return []


def fetch_weather_for_trip(
    destination: str, trip_dates: list[str]
) -> dict[str, DayWeather]:
    """Fetch weather for each day of a trip.

    Uses forecast data for dates within 16 days, historical data (same dates
    from previous year) for dates further out.

    Returns a dict mapping ISO date strings to DayWeather objects.
    """
    if not trip_dates:
        return {}

    coords = geocode_destination(destination)
    if not coords:
        logger.warning("Cannot fetch weather — geocoding failed for '%s'", destination)
        return {}

    today = date.today()
    forecast_cutoff = today + timedelta(days=16)

    # Split dates into forecast vs historical ranges
    forecast_dates = []
    historical_dates = []
    for d in trip_dates:
        try:
            trip_date = date.fromisoformat(d)
            if trip_date <= forecast_cutoff:
                forecast_dates.append(d)
            else:
                historical_dates.append(d)
        except ValueError:
            logger.warning("Invalid date format: %s", d)

    results: dict[str, DayWeather] = {}

    # Fetch forecast data
    if forecast_dates:
        forecast_weather = _fetch_forecast(
            coords, min(forecast_dates), max(forecast_dates)
        )
        for w in forecast_weather:
            if w.date in forecast_dates:
                results[w.date] = w
        logger.info("Fetched forecast weather for %d days", len(forecast_weather))

    # Fetch historical data for dates beyond forecast range
    if historical_dates:
        historical_weather = _fetch_historical(
            coords, min(historical_dates), max(historical_dates)
        )
        for w in historical_weather:
            results[w.date] = w
        logger.info(
            "Fetched historical weather for %d days (based on previous year)",
            len(historical_weather),
        )

    return results
