"""Shared geocoding helpers with local-first country resolution."""

from __future__ import annotations

from functools import lru_cache
from typing import NamedTuple

import requests

from infrastructure.logging_utils import get_logger
from infrastructure.persistence.memory_store import load_place_country, save_place_alias

logger = get_logger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

CITY_TO_COUNTRY: dict[str, str] = {
    "amsterdam": "Netherlands",
    "athens": "Greece",
    "bali": "Indonesia",
    "bangkok": "Thailand",
    "barcelona": "Spain",
    "berlin": "Germany",
    "budapest": "Hungary",
    "copenhagen": "Denmark",
    "croatia": "Croatia",
    "dubai": "UAE",
    "dubrovnik": "Croatia",
    "edinburgh": "United Kingdom",
    "france": "France",
    "germany": "Germany",
    "greece": "Greece",
    "hong kong": "Hong Kong",
    "iceland": "Iceland",
    "indonesia": "Indonesia",
    "istanbul": "Turkey",
    "italy": "Italy",
    "japan": "Japan",
    "lisbon": "Portugal",
    "london": "United Kingdom",
    "madrid": "Spain",
    "netherlands": "Netherlands",
    "new york": "United States",
    "paris": "France",
    "portugal": "Portugal",
    "prague": "Czech Republic",
    "reykjavik": "Iceland",
    "rome": "Italy",
    "seoul": "South Korea",
    "singapore": "Singapore",
    "spain": "Spain",
    "sydney": "Australia",
    "thailand": "Thailand",
    "tokyo": "Japan",
    "turkey": "Turkey",
    "uae": "UAE",
    "united kingdom": "United Kingdom",
    "united states": "United States",
    "usa": "United States",
    "vienna": "Austria",
}


class GeocodedPlace(NamedTuple):
    """Normalized geocoding result."""

    latitude: float
    longitude: float
    name: str
    country: str


def _normalise_label(value: str) -> str:
    return " ".join((value or "").lower().replace(",", " ").split())


def _lookup_local_country(destination: str) -> str:
    normalised = _normalise_label(destination)
    if not normalised:
        return ""

    if normalised in CITY_TO_COUNTRY:
        return CITY_TO_COUNTRY[normalised]

    tokens = normalised.split()
    for key, country in CITY_TO_COUNTRY.items():
        if normalised.endswith(f" {key}") or key in tokens:
            return country
    return ""


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

    local_match = _lookup_local_country(destination)
    if local_match:
        return local_match

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
