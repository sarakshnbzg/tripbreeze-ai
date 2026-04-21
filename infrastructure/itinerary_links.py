"""Helpers for enriching displayed itineraries with booking links.

These helpers are intentionally display-only. The stored itinerary text used for
PDFs, emails, and persistence should remain unmodified.
"""

from __future__ import annotations


def _insert_after_section(markdown: str, heading: str, link_line: str) -> str:
    idx = markdown.find(heading)
    if idx == -1:
        return markdown
    next_idx = markdown.find("\n#### ", idx + len(heading))
    insertion = f"\n\n{link_line}\n"
    if next_idx == -1:
        return markdown.rstrip() + insertion
    return markdown[:next_idx] + insertion + markdown[next_idx:]


def _insert_into_leg(markdown: str, leg_number: int, link_lines: list[str]) -> str:
    if not link_lines:
        return markdown

    anchor = f"**Leg {leg_number}:"
    idx = markdown.find(anchor)
    if idx == -1:
        return markdown

    next_leg_idx = markdown.find(f"\n\n**Leg {leg_number + 1}:", idx + len(anchor))
    next_section_idx = markdown.find("\n\n#### ", idx + len(anchor))
    boundaries = [pos for pos in (next_leg_idx, next_section_idx) if pos != -1]
    insert_at = min(boundaries) if boundaries else len(markdown)
    insertion = "\n" + "\n".join(link_lines)
    return markdown[:insert_at] + insertion + markdown[insert_at:]


def inject_booking_links(
    markdown: str,
    flight: dict,
    hotel: dict,
    flights: list[dict] | None = None,
    hotels: list[dict] | None = None,
) -> str:
    """Insert booking links inline after itinerary sections for display."""
    result = markdown

    flight_url = (flight or {}).get("booking_url")
    hotel_url = (hotel or {}).get("booking_url")

    if flight_url:
        airline = (flight or {}).get("airline") or "this flight"
        result = _insert_after_section(
            result,
            "#### 🛫 Flight Details",
            f"🔗 **[Book {airline} on Google Flights]({flight_url})**",
        )

    if hotel_url:
        name = (hotel or {}).get("name") or "this hotel"
        result = _insert_after_section(
            result,
            "#### 🏨 Hotel Details",
            f"🔗 **[Book {name}]({hotel_url})**",
        )

    selected_flights = flights or []
    selected_hotels = hotels or []
    total_legs = max(len(selected_flights), len(selected_hotels))
    for leg_number in range(1, total_legs + 1):
        leg_flight = selected_flights[leg_number - 1] if leg_number - 1 < len(selected_flights) else {}
        leg_hotel = selected_hotels[leg_number - 1] if leg_number - 1 < len(selected_hotels) else {}
        link_lines: list[str] = []

        leg_flight_url = leg_flight.get("booking_url")
        if leg_flight_url:
            airline = leg_flight.get("airline") or f"flight for leg {leg_number}"
            link_lines.append(f"🔗 **[Book {airline} on Google Flights]({leg_flight_url})**")

        leg_hotel_url = leg_hotel.get("booking_url")
        if leg_hotel_url:
            name = leg_hotel.get("name") or f"hotel for leg {leg_number}"
            link_lines.append(f"🔗 **[Book {name}]({leg_hotel_url})**")

        result = _insert_into_leg(result, leg_number, link_lines)

    return result
