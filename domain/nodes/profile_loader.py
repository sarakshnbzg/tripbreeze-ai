"""Profile Loader node — loads user preferences from long-term memory."""

from infrastructure.persistence.memory_store import load_profile
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def profile_loader(state: dict) -> dict:
    """LangGraph node: load user profile from persistent storage."""
    user_id = state.get("user_id", "default_user")
    logger.info("Loading profile for user_id=%s", user_id)
    profile = load_profile(user_id)
    logger.info(
        "Profile loaded for user_id=%s home_city=%s past_trips=%s",
        user_id,
        bool(profile.get("home_city")),
        len(profile.get("past_trips", [])),
    )

    return {
        "user_profile": profile,
        "messages": [{
            "role": "system",
            "content": (
                f"User profile loaded. Home city: {profile.get('home_city', 'not set')}. "
                f"Preferred class: {profile.get('travel_class', 'ECONOMY')}. "
                f"Preferred hotel stars: {profile.get('preferred_hotel_stars', []) or 'not set'}. "
                f"Passport country: {profile.get('passport_country', 'not set')}. "
                f"Past destinations: {', '.join(t['destination'] for t in profile.get('past_trips', [])) or 'none'}."
            ),
        }],
        "current_step": "profile_loaded",
    }
