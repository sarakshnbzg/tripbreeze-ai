"""Country State City API client for syncing countries and cities into reference tables."""

from __future__ import annotations

from collections.abc import Iterable

import requests

from settings import CSC_API_KEY
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

CSC_API_BASE_URL = "https://api.countrystatecity.in/v1"


def _request(path: str) -> list[dict]:
    if not CSC_API_KEY:
        raise RuntimeError("Country State City sync requires CSC_API_KEY.")

    response = requests.get(
        f"{CSC_API_BASE_URL}{path}",
        headers={"X-CSCAPI-KEY": CSC_API_KEY},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def fetch_countries() -> list[dict]:
    """Return normalized country records from Country State City API."""
    countries = _request("/countries")
    normalized: list[dict] = []
    for country in countries:
        name = str(country.get("name", "")).strip()
        iso2 = str(country.get("iso2", "")).strip()
        if not name:
            continue
        normalized.append({"name": name, "iso2": iso2})
    return normalized


def fetch_cities_for_country(iso2: str) -> list[str]:
    """Return city names for a given country ISO2 code."""
    if not iso2:
        return []
    cities = _request(f"/countries/{iso2}/cities")
    results: list[str] = []
    for city in cities:
        name = str(city.get("name", "")).strip()
        if name:
            results.append(name)
    return results


def fetch_all_city_names(countries: Iterable[dict]) -> list[str]:
    """Return deduplicated city names across all countries."""
    seen: set[str] = set()
    names: list[str] = []
    for country in countries:
        iso2 = str(country.get("iso2", "")).strip()
        for city_name in fetch_cities_for_country(iso2):
            normalized = " ".join(city_name.lower().replace(",", " ").split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            names.append(city_name)
    logger.info("Fetched %s deduplicated city names from Country State City API", len(names))
    return sorted(names)
