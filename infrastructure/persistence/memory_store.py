"""Postgres-backed persistence for long-term user profiles.

Uses a connection pool (psycopg_pool) to avoid opening a new TCP
connection on every request.  The pool is created lazily on first
use and reused for the lifetime of the process.
"""

import atexit
import bcrypt
import json
import re

from config import DAILY_EXPENSE_BY_DESTINATION, MEMORY_DATABASE_URL
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

# ── Connection pool (lazy singleton) ────────────────────────────────

_pool = None


def _get_pool():
    """Return the module-level connection pool, creating it on first call."""
    global _pool
    if _pool is not None:
        return _pool

    if not MEMORY_DATABASE_URL:
        raise RuntimeError(
            "Long-term memory requires DATABASE_URL or NEON_DATABASE_URL in your environment or Streamlit secrets."
        )

    try:
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise RuntimeError(
            "Postgres memory requires the `psycopg[binary]` and `psycopg-pool` packages. "
            "Install dependencies with `uv sync`."
        ) from exc

    _pool = ConnectionPool(
        conninfo=MEMORY_DATABASE_URL,
        min_size=1,
        max_size=5,
        open=True,
        check=ConnectionPool.check_connection,
    )
    atexit.register(_pool.close)

    # Ensure schema exists (runs once at pool creation)
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_json JSONB NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_credentials (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS place_aliases (
                    normalized_name TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    city_name TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS destination_daily_expenses (
                    normalized_name TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    daily_expense_eur DOUBLE PRECISION NOT NULL,
                    source TEXT NOT NULL DEFAULT 'seed'
                )
                """
            )
            for normalized_name, daily_expense_eur in DAILY_EXPENSE_BY_DESTINATION.items():
                cur.execute(
                    """
                    INSERT INTO destination_daily_expenses (
                        normalized_name,
                        display_name,
                        daily_expense_eur,
                        source
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(normalized_name) DO NOTHING
                    """,
                    (
                        normalized_name.strip().lower(),
                        normalized_name.strip().title(),
                        float(daily_expense_eur),
                        "seed",
                    ),
                )
        conn.commit()
    logger.info("Postgres connection pool initialised (min=1, max=5)")
    return _pool


# ── Helpers ──────────────────────────────────────────────────────────


def _sanitise_user_id(user_id: str) -> str:
    """Validate user_id to prevent path traversal."""
    if not user_id or not _SAFE_ID_RE.match(user_id):
        raise ValueError(
            f"Invalid profile ID '{user_id}'. "
            "Use only letters, digits, hyphens, and underscores."
        )
    return user_id


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


def _normalise_place_name(name: str) -> str:
    """Normalise destination aliases for consistent DB lookups."""
    return " ".join((name or "").lower().replace(",", " ").split())


# ── Public API ───────────────────────────────────────────────────────


def list_profiles() -> list[str]:
    """Return available saved profile ids."""
    with _get_pool().connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM profiles ORDER BY user_id")
            profiles = [row[0] for row in cursor.fetchall()]
    logger.info("Discovered %s saved profiles", len(profiles))
    return profiles


def load_profile(user_id: str) -> dict:
    """Load a user's stored profile, or return defaults."""
    safe_user_id = _sanitise_user_id(user_id)
    with _get_pool().connection() as conn:
        stored_profile = _load_profile_row(conn, safe_user_id)
    if stored_profile is not None:
        logger.info("Loading persisted profile from Postgres for user_id=%s", safe_user_id)
        return {"user_id": safe_user_id, **_DEFAULT_PROFILE, **stored_profile}
    logger.info("No persisted profile found for user_id=%s; using defaults", safe_user_id)
    return {"user_id": safe_user_id, **_DEFAULT_PROFILE}


def save_profile(user_id: str, profile: dict) -> None:
    """Persist the user's profile to Postgres."""
    safe_user_id = _sanitise_user_id(user_id)
    stored_profile = dict(profile)
    stored_profile["user_id"] = safe_user_id
    with _get_pool().connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO profiles (user_id, profile_json)
                VALUES (%s, %s::jsonb)
                ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json
                """,
                (safe_user_id, json.dumps(stored_profile)),
            )
        conn.commit()
    logger.info("Saved profile for user_id=%s to Postgres", safe_user_id)


def update_profile_from_trip(user_id: str, trip_data: dict) -> dict:
    """Merge information learned from the latest trip into the profile."""
    profile = load_profile(user_id)

    if trip_data.get("destination"):
        past = profile.get("past_trips", [])
        trip_entry = {
            "destination": trip_data["destination"],
            "dates": f"{trip_data.get('departure_date', '')} – {trip_data.get('return_date', '')}",
        }
        if trip_data.get("final_itinerary"):
            trip_entry["final_itinerary"] = trip_data["final_itinerary"]
        if trip_data.get("pdf_state"):
            trip_entry["pdf_state"] = trip_data["pdf_state"]
        past.append(trip_entry)
        profile["past_trips"] = past[-10:]

    if trip_data.get("home_city") and not profile.get("home_city"):
        profile["home_city"] = trip_data["home_city"]

    if trip_data.get("travel_class"):
        profile["travel_class"] = trip_data["travel_class"]

    if trip_data.get("passport_country"):
        profile["passport_country"] = trip_data["passport_country"]

    save_profile(user_id, profile)
    return profile


# ── Authentication ────────────────────────────────────────────────


def _hash_password_bcrypt(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_bcrypt_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        logger.warning("Encountered invalid bcrypt hash during verification")
        return False


def _password_meets_minimum(password: str) -> bool:
    return len(password) >= 8


def _store_credentials(connection, user_id: str, password_hash: str, salt: str) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_credentials (user_id, password_hash, salt)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE
            SET password_hash = excluded.password_hash, salt = excluded.salt
            """,
            (user_id, password_hash, salt),
        )


def register_user(user_id: str, password: str, profile: dict | None = None) -> bool:
    """Create credentials for a new user. Returns False if user_id already exists."""
    safe_user_id = _sanitise_user_id(user_id)
    if not _password_meets_minimum(password):
        raise ValueError("Password must be at least 8 characters.")

    password_hash = _hash_password_bcrypt(password)
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM user_credentials WHERE user_id = %s", (safe_user_id,))
            if cur.fetchone() is not None:
                return False
            _store_credentials(conn, safe_user_id, password_hash, "")
        conn.commit()
    # Ensure a profile row exists for the new user.
    initial_profile = {**load_profile(safe_user_id), **(profile or {}), "user_id": safe_user_id}
    save_profile(safe_user_id, initial_profile)
    logger.info("Registered new user user_id=%s", safe_user_id)
    return True


def verify_user(user_id: str, password: str) -> bool:
    """Check credentials. Returns True on success."""
    safe_user_id = _sanitise_user_id(user_id)
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash, salt FROM user_credentials WHERE user_id = %s",
                (safe_user_id,),
            )
            row = cur.fetchone()
    if row is None:
        return False
    stored_hash, _salt = row
    return _verify_bcrypt_password(password, stored_hash)


def load_place_country(destination: str) -> str:
    """Load a country mapping for a destination alias from Postgres."""
    normalized_name = _normalise_place_name(destination)
    if not normalized_name:
        return ""

    pool = _get_pool()
    try:
        connection_context = pool.connection(timeout=1)
    except TypeError:
        connection_context = pool.connection()

    with connection_context as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT country_name FROM place_aliases WHERE normalized_name = %s",
                (normalized_name,),
            )
            row = cursor.fetchone()
    if row is None:
        return ""
    return str(row[0] or "").strip()


def save_place_alias(
    destination: str,
    *,
    country_name: str,
    city_name: str | None = None,
    display_name: str | None = None,
    source: str = "manual",
) -> None:
    """Persist a normalized destination alias for future country lookups."""
    normalized_name = _normalise_place_name(destination)
    if not normalized_name or not country_name.strip():
        return

    pool = _get_pool()
    try:
        connection_context = pool.connection(timeout=1)
    except TypeError:
        connection_context = pool.connection()

    with connection_context as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO place_aliases (
                    normalized_name,
                    display_name,
                    city_name,
                    country_name,
                    source
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(normalized_name) DO UPDATE SET
                    display_name = excluded.display_name,
                    city_name = excluded.city_name,
                    country_name = excluded.country_name,
                    source = excluded.source
                """,
                (
                    normalized_name,
                    (display_name or destination).strip(),
                    (city_name or destination).strip(),
                    country_name.strip(),
                    source.strip() or "manual",
                ),
            )
        conn.commit()


def load_destination_daily_expense(destination: str) -> tuple[float | None, str]:
    """Load a destination daily-expense baseline in EUR from Postgres.

    Returns the matched EUR baseline and the normalized key that matched.
    Falls back from exact alias lookups to substring matching against all
    stored baseline keys so inputs like "Paris, France" still resolve.
    """
    normalized_destination = _normalise_place_name(destination)
    if not normalized_destination:
        return None, ""

    pool = _get_pool()
    try:
        connection_context = pool.connection(timeout=1)
    except TypeError:
        connection_context = pool.connection()

    with connection_context as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT normalized_name, daily_expense_eur
                FROM destination_daily_expenses
                WHERE normalized_name = %s
                """,
                (normalized_destination,),
            )
            row = cursor.fetchone()
            if row is not None:
                return float(row[1]), str(row[0])

            cursor.execute(
                """
                SELECT normalized_name, daily_expense_eur
                FROM destination_daily_expenses
                ORDER BY normalized_name
                """
            )
            rows = cursor.fetchall()

    for normalized_name, daily_expense_eur in rows:
        if str(normalized_name) and str(normalized_name) in normalized_destination:
            return float(daily_expense_eur), str(normalized_name)
    return None, ""


def save_destination_daily_expense(
    destination: str,
    *,
    daily_expense_eur: float,
    display_name: str | None = None,
    source: str = "manual",
) -> None:
    """Persist a destination daily-expense baseline in EUR."""
    normalized_name = _normalise_place_name(destination)
    if not normalized_name:
        return

    pool = _get_pool()
    try:
        connection_context = pool.connection(timeout=1)
    except TypeError:
        connection_context = pool.connection()

    with connection_context as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO destination_daily_expenses (
                    normalized_name,
                    display_name,
                    daily_expense_eur,
                    source
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(normalized_name) DO UPDATE SET
                    display_name = excluded.display_name,
                    daily_expense_eur = excluded.daily_expense_eur,
                    source = excluded.source
                """,
                (
                    normalized_name,
                    (display_name or destination).strip(),
                    float(daily_expense_eur),
                    source.strip() or "manual",
                ),
            )
        conn.commit()
