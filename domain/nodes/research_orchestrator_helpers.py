"""Deterministic helper functions for the research orchestrator."""

import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import KNOWLEDGE_BASE_DIR
from infrastructure.apis.geocoding_client import resolve_destination_country as _geocoding_resolve_destination_country
from infrastructure.persistence.memory_store import list_place_aliases as _memory_store_list_place_aliases

DESTINATION_INFO_SECTIONS = (
    ("entry_requirements", "🛂 Entry Requirements"),
)

_VISA_REQUIREMENTS_PATH = KNOWLEDGE_BASE_DIR / "visa_requirements.md"


def resolve_destination_country(destination: str) -> str:
    """Compatibility wrapper kept patchable for tests and callers."""
    orchestrator_module = sys.modules.get("domain.nodes.research_orchestrator")
    orchestrator_override = getattr(orchestrator_module, "resolve_destination_country", None)
    if orchestrator_override is not None and orchestrator_override is not resolve_destination_country:
        return orchestrator_override(destination)
    return _geocoding_resolve_destination_country(destination)


def list_place_aliases() -> list[dict[str, Any]]:
    """Compatibility wrapper kept patchable for tests and callers."""
    orchestrator_module = sys.modules.get("domain.nodes.research_orchestrator")
    orchestrator_override = getattr(orchestrator_module, "list_place_aliases", None)
    if orchestrator_override is not None and orchestrator_override is not list_place_aliases:
        return orchestrator_override()
    return _memory_store_list_place_aliases()


@lru_cache(maxsize=1)
def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalise_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _section_body(markdown: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _resolve_passport_country(trip_request: dict[str, Any], user_profile: dict[str, Any]) -> str:
    return str(
        trip_request.get("passport_country")
        or user_profile.get("passport_country")
        or ""
    ).strip()


def _resolve_destination_country(destination: str) -> str:
    country = resolve_destination_country(destination)
    if country:
        return country
    return _fallback_destination_country(destination)


@lru_cache(maxsize=1)
def _place_alias_country_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    try:
        aliases = list_place_aliases()
    except Exception:
        return alias_map

    for alias in aliases:
        country = str(alias.get("country_name", "")).strip()
        if not country:
            continue
        for key in (
            alias.get("normalized_name"),
            alias.get("display_name"),
            alias.get("city_name"),
            alias.get("country_name"),
        ):
            normalised = _normalise_label(str(key or ""))
            if normalised and normalised not in alias_map:
                alias_map[normalised] = country
    return alias_map


def _fallback_destination_country(destination: str) -> str:
    return _place_alias_country_map().get(_normalise_label(destination), "")


def _append_source(sources: list[str], label: str) -> None:
    if label not in sources:
        sources.append(label)


def _ordered_unique_destinations(trip_legs: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for leg in trip_legs:
        if not leg.get("needs_hotel"):
            continue
        destination = str(leg.get("destination", "")).strip()
        if not destination:
            continue
        key = _normalise_label(destination)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(destination)

    return ordered


def _lookup_entry_requirements(destination: str, passport_country: str) -> str:
    country = _resolve_destination_country(destination)
    if not country:
        return ""

    visa_markdown = _read_text(_VISA_REQUIREMENTS_PATH)
    visa_heading = ""
    country_key = _normalise_label(country)

    for match in re.finditer(r"^##\s+(.+)$", visa_markdown, flags=re.MULTILINE):
        heading = match.group(1).strip()
        heading_country = heading.split("(", 1)[0].strip()
        if _normalise_label(heading_country) == country_key:
            visa_heading = heading
            break

    if not visa_heading:
        return ""

    body = _section_body(visa_markdown, visa_heading)
    selected_lines: list[str] = []
    passport_key = _normalise_label(passport_country)

    if passport_key:
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- **"):
                continue
            label_match = re.match(r"- \*\*(.+?):\*\*", stripped)
            if not label_match:
                continue
            if _normalise_label(label_match.group(1)).startswith(passport_key):
                selected_lines.append(f"{stripped} (Source: Visa Requirements)")
                break

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **Documents needed:**"):
            selected_lines.append(f"{stripped} (Source: Visa Requirements)")
            break

    if not selected_lines:
        return ""

    return f"### {visa_heading}\n" + "\n".join(selected_lines)


def _maybe_use_precise_destination_info(
    final_result: dict[str, Any],
    trip_request: dict[str, Any],
    user_profile: dict[str, Any],
    rag_sources: list[str],
) -> dict[str, Any]:
    destination = str(trip_request.get("destination", "")).strip()
    passport_country = _resolve_passport_country(trip_request, user_profile)
    if not destination:
        return final_result

    enriched = dict(final_result)
    entry_requirements = _lookup_entry_requirements(destination, passport_country)

    if entry_requirements:
        enriched["entry_requirements"] = entry_requirements
        _append_source(rag_sources, "Visa Requirements")

    return enriched


def _enrich_retrieval_query(query: str, trip_request: dict[str, Any], user_profile: dict[str, Any]) -> str:
    """Always inject destination and passport country into retrieval queries."""
    destination = trip_request.get("destination", "")
    passport_country = _resolve_passport_country(trip_request, user_profile)

    additions = []
    if passport_country and passport_country.lower() not in query.lower():
        additions.append(f"for travelers with a passport from {passport_country}")
    if destination and destination.lower() not in query.lower():
        additions.append(f"visiting {destination}")

    if not additions:
        return query

    return f"{query.strip()} {' '.join(additions)}".strip()


def _build_research_summary(results: dict[str, Any], final_response: str) -> str:
    text = final_response.strip()

    marker = "Destination briefing:"
    if marker in text:
        text = text.split(marker, 1)[0].strip()

    if text:
        return text

    parts = ["Research complete."]
    if results.get("flight_options") is not None:
        parts.append(f"Flights found: {len(results.get('flight_options', []))}.")
    if results.get("hotel_options") is not None:
        parts.append(f"Hotels found: {len(results.get('hotel_options', []))}.")
    if results.get("destination_info"):
        parts.append("Destination briefing prepared.")
    return " ".join(parts)


def _format_destination_info(final_result: dict[str, Any]) -> str:
    """Format structured destination fields into a stable user-facing briefing."""
    sections = []
    for field_name, heading in DESTINATION_INFO_SECTIONS:
        content = str(final_result.get(field_name, "")).strip()
        if content:
            sections.append(f"#### {heading}\n{content}")

    if sections:
        return "\n\n".join(
            [
                "A quick travel snapshot to help you compare options and plan the stay:",
                *sections,
            ]
        )

    return str(final_result.get("destination_briefing", "")).strip()
