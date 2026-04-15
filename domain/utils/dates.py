"""Shared date and trip duration utilities."""

from datetime import date, timedelta


def parse_trip_dates(trip: dict) -> tuple[date | None, date | None]:
    """Extract and parse departure and end dates from a trip dict.

    Returns (departure_date, end_date) where end_date is return_date or check_out_date.
    Returns None for either date if missing or invalid.
    """
    departure_str = trip.get("departure_date", "")
    end_str = trip.get("return_date", "") or trip.get("check_out_date", "")

    departure = None
    end = None

    if departure_str:
        try:
            departure = date.fromisoformat(departure_str)
        except ValueError:
            pass

    if end_str:
        try:
            end = date.fromisoformat(end_str)
        except ValueError:
            pass

    return departure, end


def trip_duration_days(trip: dict, default: int = 1) -> int:
    """Calculate trip duration in days.

    Returns the number of days between departure and return/check-out dates.
    Returns default (minimum 1) if dates are missing or invalid.
    """
    departure, end = parse_trip_dates(trip)
    if departure is None or end is None:
        return max(default, 1)
    return max((end - departure).days, 1)


def trip_duration_with_dates(trip: dict) -> tuple[int, list[str]]:
    """Calculate trip duration and return a list of ISO date strings for each day.

    Returns (num_days, [ISO date strings]) where each date is a day of the trip.
    Returns (0, []) if departure date is missing or invalid.
    """
    departure, end = parse_trip_dates(trip)
    if departure is None:
        return 0, []

    if end is not None:
        num_days = max(1, (end - departure).days)
    else:
        num_days = 1

    return num_days, [(departure + timedelta(days=i)).isoformat() for i in range(num_days)]


def trip_duration_display(trip: dict) -> int | str:
    """Calculate trip duration for display purposes.

    Returns the number of nights, or '?' if dates are missing or invalid.
    Useful for UI display where '?' indicates unknown duration.
    """
    departure, end = parse_trip_dates(trip)
    if departure is None or end is None:
        return "?"
    return max((end - departure).days, 1)


def validate_future_date(value: str, field_name: str) -> str:
    """Validate a date string is YYYY-MM-DD format and not in the past.

    Args:
        value: Date string to validate (empty string is allowed)
        field_name: Name of the field for error messages

    Returns:
        The validated date string, or empty string if input was empty

    Raises:
        ValueError: If date format is invalid or date is in the past
    """
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field_name} '{value}' is not a valid date (expected YYYY-MM-DD).")
    if parsed < date.today():
        raise ValueError(f"{field_name} ({value}) is in the past.")
    return value
