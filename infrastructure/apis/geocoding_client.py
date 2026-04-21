"""Shared geocoding helpers with local-first country resolution."""

from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import NamedTuple

import requests

from infrastructure.logging_utils import get_logger
from infrastructure.persistence.memory_store import load_place_country, save_place_alias

logger = get_logger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Nominatim (OpenStreetMap) for free-form address geocoding.
# Usage policy: max 1 req/s and a descriptive User-Agent.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "tripbreeze-ai/0.1 (itinerary map feature)"
_NOMINATIM_MIN_INTERVAL_S = 1.05
_nominatim_lock = threading.Lock()
_nominatim_last_request_ts = 0.0


class GeocodedPlace(NamedTuple):
    """Normalized geocoding result."""

    latitude: float
    longitude: float
    name: str
    country: str

def _country_from_geocode_payload(payload: dict, destination: str) -> str:
    for result in payload.get("results", []) or []:
        country = str(result.get("country", "") or "").strip()
        if country:
            return country
    logger.warning("Geocoding found no country for '%s'", destination)
    return ""


def _fetch_geocode_payload(destination: str) -> dict | None:
    """Fetch raw geocoder payload for a destination."""
    if not (destination or "").strip():
        return None

    try:
        response = requests.get(
            GEOCODE_URL,
            params={
                "name": destination,
                "count": 3,
                "language": "en",
                "format": "json",
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Destination geocoding failed for '%s': %s", destination, exc)
        return None

    return response.json()


@lru_cache(maxsize=256)
def geocode_place(destination: str) -> GeocodedPlace | None:
    """Resolve a destination string to a normalized place record."""
    payload = _fetch_geocode_payload(destination)
    if payload is None:
        return None

    for result in payload.get("results", []) or []:
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        if latitude is None or longitude is None:
            continue
        place = GeocodedPlace(
            latitude=float(latitude),
            longitude=float(longitude),
            name=str(result.get("name", destination) or destination),
            country=str(result.get("country", "") or "").strip(),
        )
        logger.info(
            "Geocoded '%s' to %s (%.4f, %.4f)%s",
            destination,
            place.name,
            place.latitude,
            place.longitude,
            f" in {place.country}" if place.country else "",
        )
        return place

    logger.warning("Geocoding found no results for '%s'", destination)
    return None


def _nominatim_throttle() -> None:
    """Enforce Nominatim's 1 req/s usage policy across threads."""
    global _nominatim_last_request_ts
    with _nominatim_lock:
        now = time.monotonic()
        wait = _NOMINATIM_MIN_INTERVAL_S - (now - _nominatim_last_request_ts)
        if wait > 0:
            time.sleep(wait)
        _nominatim_last_request_ts = time.monotonic()


@lru_cache(maxsize=1024)
def geocode_address(query: str) -> tuple[float, float] | None:
    """Resolve a free-form address or landmark to (latitude, longitude).

    Uses Nominatim (OpenStreetMap). Results are cached in-process. Returns
    None if the query is empty or the lookup fails.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return None

    _nominatim_throttle()
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": cleaned, "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Address geocoding failed for '%s': %s", cleaned, exc)
        return None

    try:
        results = response.json() or []
    except ValueError:
        logger.warning("Address geocoding returned non-JSON for '%s'", cleaned)
        return None

    for result in results:
        lat = result.get("lat")
        lon = result.get("lon")
        if lat is None or lon is None:
            continue
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            continue

    logger.info("Address geocoding found no results for '%s'", cleaned)
    return None


@lru_cache(maxsize=256)
def resolve_destination_country(destination: str) -> str:
    """Resolve a destination string to a country name."""
    try:
        db_match = load_place_country(destination)
    except Exception as exc:
        logger.warning("DB place lookup failed for '%s': %s", destination, exc)
        db_match = ""
    if db_match:
        return db_match

    payload = _fetch_geocode_payload(destination)
    if payload is None:
        return ""

    country = _country_from_geocode_payload(payload, destination)
    if country:
        logger.info("Resolved destination '%s' to country '%s' via geocoder", destination, country)
        try:
            save_place_alias(destination, country_name=country, source="geocoder")
        except Exception as exc:
            logger.warning("Saving geocoded place alias failed for '%s': %s", destination, exc)
        return country
    return ""
