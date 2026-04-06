"""JSON-file persistence for long-term user profiles.

This is the only module that reads/writes user profile files.
"""

import json
import re

from config import MEMORY_DIR
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

MEMORY_DIR.mkdir(exist_ok=True)

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


def _user_file(user_id: str):
    return MEMORY_DIR / f"{_sanitise_user_id(user_id)}.json"


def list_profiles() -> list[str]:
    """Return available saved profile ids."""
    profiles = sorted(path.stem for path in MEMORY_DIR.glob("*.json"))
    logger.info("Discovered %s saved profiles", len(profiles))
    return profiles


def load_profile(user_id: str) -> dict:
    """Load a user's stored profile, or return defaults."""
    path = _user_file(user_id)
    if path.exists():
        logger.info("Loading persisted profile from %s", path)
        stored_profile = json.loads(path.read_text())
        return {"user_id": user_id, **_DEFAULT_PROFILE, **stored_profile}
    logger.info("No persisted profile found for user_id=%s; using defaults", user_id)
    return {"user_id": user_id, **_DEFAULT_PROFILE}


def save_profile(user_id: str, profile: dict) -> None:
    """Persist the user's profile to disk."""
    profile["user_id"] = user_id
    path = _user_file(user_id)
    path.write_text(json.dumps(profile, indent=2))
    logger.info("Saved profile for user_id=%s to %s", user_id, path)


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
