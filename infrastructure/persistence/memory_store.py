"""Postgres-backed persistence for long-term user profiles."""

import json
import re

from config import MEMORY_DATABASE_URL
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

_DEFAULT_PROFILE = {
    "preferred_airlines": [],
    "preferred_hotel_stars": [],
    "preferred_outbound_time_window": [0, 23],
    "preferred_return_time_window": [0, 23],
    "travel_class": "ECONOMY",
    "home_city": "",
    "passport_country": "",
    "past_trips": [],
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _sanitise_user_id(user_id: str) -> str:
    """Validate user_id to prevent path traversal."""
    if not user_id or not _SAFE_ID_RE.match(user_id):
        raise ValueError(
            f"Invalid profile ID '{user_id}'. "
            "Use only letters, digits, hyphens, and underscores."
        )
    return user_id


def _connect():
    """Open the Postgres memory database and ensure schema exists."""
    if not MEMORY_DATABASE_URL:
        raise RuntimeError(
            "Long-term memory requires DATABASE_URL or NEON_DATABASE_URL in your environment or Streamlit secrets."
        )

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Postgres memory requires the `psycopg[binary]` package. Install dependencies with `uv sync`."
        ) from exc

    connection = psycopg.connect(MEMORY_DATABASE_URL)
    with connection.cursor() as cursor:
        cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY,
            profile_json JSONB NOT NULL
        )
        """
        )
    connection.commit()
    return connection


def _load_profile_row(connection, user_id: str) -> dict | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT profile_json FROM profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    profile_json = row[0]
    return profile_json if isinstance(profile_json, dict) else json.loads(profile_json)


def list_profiles() -> list[str]:
    """Return available saved profile ids."""
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM profiles ORDER BY user_id")
            profiles = [row[0] for row in cursor.fetchall()]
    logger.info("Discovered %s saved profiles", len(profiles))
    return profiles


def load_profile(user_id: str) -> dict:
    """Load a user's stored profile, or return defaults."""
    safe_user_id = _sanitise_user_id(user_id)
    with _connect() as connection:
        stored_profile = _load_profile_row(connection, safe_user_id)
    if stored_profile is not None:
        logger.info("Loading persisted profile from Postgres for user_id=%s", safe_user_id)
        return {"user_id": safe_user_id, **_DEFAULT_PROFILE, **stored_profile}
    logger.info("No persisted profile found for user_id=%s; using defaults", user_id)
    return {"user_id": safe_user_id, **_DEFAULT_PROFILE}


def save_profile(user_id: str, profile: dict) -> None:
    """Persist the user's profile to Postgres."""
    safe_user_id = _sanitise_user_id(user_id)
    stored_profile = dict(profile)
    stored_profile["user_id"] = safe_user_id
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO profiles (user_id, profile_json)
            VALUES (%s, %s::jsonb)
            ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json
            """,
            (safe_user_id, json.dumps(stored_profile)),
            )
        connection.commit()
    logger.info("Saved profile for user_id=%s to Postgres", safe_user_id)


def update_profile_from_trip(user_id: str, trip_data: dict) -> dict:
    """Merge information learned from the latest trip into the profile."""
    profile = load_profile(user_id)

    if trip_data.get("destination"):
        past = profile.get("past_trips", [])
        past.append({
            "destination": trip_data["destination"],
            "dates": f"{trip_data.get('departure_date', '')} – {trip_data.get('return_date', '')}",
        })
        profile["past_trips"] = past[-10:]

    if trip_data.get("home_city") and not profile.get("home_city"):
        profile["home_city"] = trip_data["home_city"]

    if trip_data.get("travel_class"):
        profile["travel_class"] = trip_data["travel_class"]

    if trip_data.get("passport_country"):
        profile["passport_country"] = trip_data["passport_country"]

    save_profile(user_id, profile)
    return profile
