"""Postgres-backed persistence for long-term user profiles.

Uses a connection pool (psycopg_pool) to avoid opening a new TCP
connection on every request.  The pool is created lazily on first
use and reused for the lifetime of the process.
"""

import atexit
import bcrypt
import json
import re
import secrets
import threading
import time
from functools import lru_cache

from settings import MEMORY_DATABASE_URL
from infrastructure.logging_utils import get_logger
from infrastructure.apis.country_state_city_client import fetch_all_city_names, fetch_countries
from infrastructure.persistence.reference_seed_data import (
    AIRLINES,
    CITY_TO_AIRPORT,
    DAILY_EXPENSE_BY_DESTINATION,
)

logger = get_logger(__name__)

_DEFAULT_PLACE_ALIASES = (
    {"normalized_name": "amsterdam", "display_name": "Amsterdam", "city_name": "Amsterdam", "country_name": "Netherlands"},
    {"normalized_name": "athens", "display_name": "Athens", "city_name": "Athens", "country_name": "Greece"},
    {"normalized_name": "bali", "display_name": "Bali", "city_name": "Bali", "country_name": "Indonesia"},
    {"normalized_name": "bangkok", "display_name": "Bangkok", "city_name": "Bangkok", "country_name": "Thailand"},
    {"normalized_name": "barcelona", "display_name": "Barcelona", "city_name": "Barcelona", "country_name": "Spain"},
    {"normalized_name": "berlin", "display_name": "Berlin", "city_name": "Berlin", "country_name": "Germany"},
    {"normalized_name": "budapest", "display_name": "Budapest", "city_name": "Budapest", "country_name": "Hungary"},
    {"normalized_name": "copenhagen", "display_name": "Copenhagen", "city_name": "Copenhagen", "country_name": "Denmark"},
    {"normalized_name": "croatia", "display_name": "Croatia", "city_name": "Croatia", "country_name": "Croatia"},
    {"normalized_name": "cork", "display_name": "Cork", "city_name": "Cork", "country_name": "Ireland"},
    {"normalized_name": "dubai", "display_name": "Dubai", "city_name": "Dubai", "country_name": "UAE"},
    {"normalized_name": "dubrovnik", "display_name": "Dubrovnik", "city_name": "Dubrovnik", "country_name": "Croatia"},
    {"normalized_name": "dublin", "display_name": "Dublin", "city_name": "Dublin", "country_name": "Ireland"},
    {"normalized_name": "edinburgh", "display_name": "Edinburgh", "city_name": "Edinburgh", "country_name": "United Kingdom"},
    {"normalized_name": "france", "display_name": "France", "city_name": "France", "country_name": "France"},
    {"normalized_name": "geneva", "display_name": "Geneva", "city_name": "Geneva", "country_name": "Switzerland"},
    {"normalized_name": "germany", "display_name": "Germany", "city_name": "Germany", "country_name": "Germany"},
    {"normalized_name": "greece", "display_name": "Greece", "city_name": "Greece", "country_name": "Greece"},
    {"normalized_name": "hong kong", "display_name": "Hong Kong", "city_name": "Hong Kong", "country_name": "Hong Kong"},
    {"normalized_name": "iceland", "display_name": "Iceland", "city_name": "Iceland", "country_name": "Iceland"},
    {"normalized_name": "indonesia", "display_name": "Indonesia", "city_name": "Indonesia", "country_name": "Indonesia"},
    {"normalized_name": "istanbul", "display_name": "Istanbul", "city_name": "Istanbul", "country_name": "Turkey"},
    {"normalized_name": "italy", "display_name": "Italy", "city_name": "Italy", "country_name": "Italy"},
    {"normalized_name": "japan", "display_name": "Japan", "city_name": "Japan", "country_name": "Japan"},
    {"normalized_name": "lisbon", "display_name": "Lisbon", "city_name": "Lisbon", "country_name": "Portugal"},
    {"normalized_name": "london", "display_name": "London", "city_name": "London", "country_name": "United Kingdom"},
    {"normalized_name": "lucerne", "display_name": "Lucerne", "city_name": "Lucerne", "country_name": "Switzerland"},
    {"normalized_name": "madrid", "display_name": "Madrid", "city_name": "Madrid", "country_name": "Spain"},
    {"normalized_name": "manila", "display_name": "Manila", "city_name": "Manila", "country_name": "Philippines"},
    {"normalized_name": "netherlands", "display_name": "Netherlands", "city_name": "Netherlands", "country_name": "Netherlands"},
    {"normalized_name": "new york", "display_name": "New York", "city_name": "New York", "country_name": "United States"},
    {"normalized_name": "oslo", "display_name": "Oslo", "city_name": "Oslo", "country_name": "Norway"},
    {"normalized_name": "paris", "display_name": "Paris", "city_name": "Paris", "country_name": "France"},
    {"normalized_name": "portugal", "display_name": "Portugal", "city_name": "Portugal", "country_name": "Portugal"},
    {"normalized_name": "prague", "display_name": "Prague", "city_name": "Prague", "country_name": "Czech Republic"},
    {"normalized_name": "reykjavik", "display_name": "Reykjavik", "city_name": "Reykjavik", "country_name": "Iceland"},
    {"normalized_name": "rome", "display_name": "Rome", "city_name": "Rome", "country_name": "Italy"},
    {"normalized_name": "seoul", "display_name": "Seoul", "city_name": "Seoul", "country_name": "South Korea"},
    {"normalized_name": "singapore", "display_name": "Singapore", "city_name": "Singapore", "country_name": "Singapore"},
    {"normalized_name": "spain", "display_name": "Spain", "city_name": "Spain", "country_name": "Spain"},
    {"normalized_name": "sydney", "display_name": "Sydney", "city_name": "Sydney", "country_name": "Australia"},
    {"normalized_name": "thailand", "display_name": "Thailand", "city_name": "Thailand", "country_name": "Thailand"},
    {"normalized_name": "tokyo", "display_name": "Tokyo", "city_name": "Tokyo", "country_name": "Japan"},
    {"normalized_name": "turkey", "display_name": "Turkey", "city_name": "Turkey", "country_name": "Turkey"},
    {"normalized_name": "uae", "display_name": "UAE", "city_name": "UAE", "country_name": "UAE"},
    {"normalized_name": "united kingdom", "display_name": "United Kingdom", "city_name": "United Kingdom", "country_name": "United Kingdom"},
    {"normalized_name": "united states", "display_name": "United States", "city_name": "United States", "country_name": "United States"},
    {"normalized_name": "usa", "display_name": "USA", "city_name": "USA", "country_name": "United States"},
    {"normalized_name": "vienna", "display_name": "Vienna", "city_name": "Vienna", "country_name": "Austria"},
    {"normalized_name": "zurich", "display_name": "Zurich", "city_name": "Zurich", "country_name": "Switzerland"},
)

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
_pool_lock = threading.Lock()
_in_memory_sessions: dict[str, dict[str, int | str]] = {}
_in_memory_sessions_lock = threading.Lock()


def _get_pool():
    """Return the module-level connection pool, creating it on first call."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
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
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_token TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expires_at BIGINT NOT NULL,
                        last_seen_at BIGINT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE user_sessions
                    ADD COLUMN IF NOT EXISTS last_seen_at BIGINT
                    """
                )
                cur.execute(
                    """
                    UPDATE user_sessions
                    SET last_seen_at = expires_at
                    WHERE last_seen_at IS NULL
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
                for alias in _DEFAULT_PLACE_ALIASES:
                    cur.execute(
                        """
                        INSERT INTO place_aliases (
                            normalized_name,
                            display_name,
                            city_name,
                            country_name,
                            source
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT(normalized_name) DO NOTHING
                        """,
                        (
                            alias["normalized_name"],
                            alias["display_name"],
                            alias["city_name"],
                            alias["country_name"],
                            "seed",
                        ),
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
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reference_options (
                        category TEXT NOT NULL,
                        normalized_name TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        value_code TEXT,
                        source TEXT NOT NULL DEFAULT 'seed',
                        PRIMARY KEY (category, normalized_name)
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
                for category, records in _REFERENCE_SEED_DATA.items():
                    for normalized_name, display_name, value_code in records:
                        cur.execute(
                            """
                            INSERT INTO reference_options (
                                category,
                                normalized_name,
                                display_name,
                                value_code,
                                source
                            )
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT(category, normalized_name) DO NOTHING
                            """,
                            (
                                category,
                                normalized_name,
                                display_name,
                                value_code,
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


_REFERENCE_SEED_DATA: dict[str, list[tuple[str, str, str | None]]] = {
    "airlines": [
        (_normalise_place_name(value), value, None)
        for value in AIRLINES
        if value
    ],
    "airport_cities": [
        (_normalise_place_name(city), city, airport_code)
        for city, airport_code in CITY_TO_AIRPORT.items()
    ],
}


def _sync_country_state_city_reference_options() -> None:
    """Populate countries and cities reference options from Country State City API."""
    countries = fetch_countries()
    city_names = fetch_all_city_names(countries)

    pool = _get_pool()
    try:
        connection_context = pool.connection(timeout=1)
    except TypeError:
        connection_context = pool.connection()

    with connection_context as conn:
        with conn.cursor() as cursor:
            for country in countries:
                name = str(country.get("name", "")).strip()
                if not name:
                    continue
                cursor.execute(
                    """
                    INSERT INTO reference_options (
                        category,
                        normalized_name,
                        display_name,
                        value_code,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(category, normalized_name) DO NOTHING
                    """,
                    (
                        "countries",
                        _normalise_place_name(name),
                        name,
                        str(country.get("iso2", "")).strip() or None,
                        "csc",
                    ),
                )
            for city_name in city_names:
                cursor.execute(
                    """
                    INSERT INTO reference_options (
                        category,
                        normalized_name,
                        display_name,
                        value_code,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(category, normalized_name) DO NOTHING
                    """,
                    (
                        "cities",
                        _normalise_place_name(city_name),
                        city_name,
                        None,
                        "csc",
                    ),
                )
        conn.commit()


def sync_country_state_city_reference_options() -> None:
    """Public wrapper for syncing CSC-backed country and city reference data."""
    list_reference_values.cache_clear()
    _sync_country_state_city_reference_options()


# ── Public API ───────────────────────────────────────────────────────


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
    """Merge information learned from the latest trip into the profile.

    Runs as a single DB transaction with row-level locking to prevent
    concurrent trip completions for the same user from overwriting each other.
    """
    safe_user_id = _sanitise_user_id(user_id)
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT profile_json FROM profiles WHERE user_id = %s FOR UPDATE",
                (safe_user_id,),
            )
            row = cur.fetchone()

        if row is not None:
            stored = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            profile = {"user_id": safe_user_id, **_DEFAULT_PROFILE, **stored}
        else:
            profile = {"user_id": safe_user_id, **_DEFAULT_PROFILE}

        if trip_data.get("destination"):
            past = profile.get("past_trips", [])
            trip_entry = {
                "destination": trip_data["destination"],
                "dates": f"{trip_data.get('departure_date', '')} – {trip_data.get('return_date', '')}",
            }
            if trip_data.get("trip_legs"):
                trip_entry["trip_legs"] = trip_data["trip_legs"]
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

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO profiles (user_id, profile_json)
                VALUES (%s, %s::jsonb)
                ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json
                """,
                (safe_user_id, json.dumps(profile)),
            )
        conn.commit()

    logger.info("Saved profile for user_id=%s to Postgres", safe_user_id)
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


def _purge_expired_in_memory_sessions(idle_timeout_seconds: int | None = None) -> None:
    now = int(time.time())
    expired = [
        token
        for token, session in _in_memory_sessions.items()
        if int(session["expires_at"]) <= now
        or (
            idle_timeout_seconds is not None
            and now - int(session["last_seen_at"]) > int(idle_timeout_seconds)
        )
    ]
    for token in expired:
        _in_memory_sessions.pop(token, None)


def create_user_session(
    user_id: str,
    ttl_seconds: int,
    *,
    idle_timeout_seconds: int | None = None,
    rotate_existing: bool = False,
) -> str:
    """Create a new opaque session token for the user."""
    safe_user_id = _sanitise_user_id(user_id)
    now = int(time.time())
    expires_at = now + int(ttl_seconds)
    session_token = secrets.token_urlsafe(32)

    if not MEMORY_DATABASE_URL:
        with _in_memory_sessions_lock:
            _purge_expired_in_memory_sessions(idle_timeout_seconds)
            if rotate_existing:
                stale_tokens = [
                    token
                    for token, session in _in_memory_sessions.items()
                    if session["user_id"] == safe_user_id
                ]
                for token in stale_tokens:
                    _in_memory_sessions.pop(token, None)
            _in_memory_sessions[session_token] = {
                "user_id": safe_user_id,
                "expires_at": expires_at,
                "last_seen_at": now,
            }
        return session_token

    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            if rotate_existing:
                cur.execute("DELETE FROM user_sessions WHERE user_id = %s", (safe_user_id,))
            cur.execute(
                """
                INSERT INTO user_sessions (session_token, user_id, expires_at, last_seen_at)
                VALUES (%s, %s, %s, %s)
                """,
                (session_token, safe_user_id, expires_at, now),
            )
        conn.commit()
    return session_token


def get_user_for_session(session_token: str, *, idle_timeout_seconds: int | None = None) -> str | None:
    """Resolve an opaque session token to a user id if still valid."""
    token = str(session_token or "").strip()
    if not token:
        return None

    now = int(time.time())
    if not MEMORY_DATABASE_URL:
        with _in_memory_sessions_lock:
            _purge_expired_in_memory_sessions(idle_timeout_seconds)
            entry = _in_memory_sessions.get(token)
            if not entry:
                return None
            expires_at = int(entry["expires_at"])
            last_seen_at = int(entry["last_seen_at"])
            if expires_at <= now:
                _in_memory_sessions.pop(token, None)
                return None
            if idle_timeout_seconds is not None and now - last_seen_at > int(idle_timeout_seconds):
                _in_memory_sessions.pop(token, None)
                return None
            entry["last_seen_at"] = now
            return str(entry["user_id"])

    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, expires_at, last_seen_at FROM user_sessions WHERE session_token = %s",
                (token,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            user_id, expires_at, last_seen_at = row
            if int(expires_at) <= now:
                cur.execute("DELETE FROM user_sessions WHERE session_token = %s", (token,))
                conn.commit()
                return None
            if idle_timeout_seconds is not None and now - int(last_seen_at) > int(idle_timeout_seconds):
                cur.execute("DELETE FROM user_sessions WHERE session_token = %s", (token,))
                conn.commit()
                return None
            cur.execute(
                "UPDATE user_sessions SET last_seen_at = %s WHERE session_token = %s",
                (now, token),
            )
            conn.commit()
    return str(user_id)


def delete_user_session(session_token: str) -> None:
    """Invalidate a specific session token."""
    token = str(session_token or "").strip()
    if not token:
        return

    if not MEMORY_DATABASE_URL:
        with _in_memory_sessions_lock:
            _in_memory_sessions.pop(token, None)
        return

    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE session_token = %s", (token,))
        conn.commit()


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
    if row is not None:
        return str(row[0] or "").strip()

    for alias in _DEFAULT_PLACE_ALIASES:
        if alias["normalized_name"] == normalized_name:
            return str(alias["country_name"]).strip()
    return ""


def list_place_aliases() -> list[dict[str, str]]:
    """Return all known place aliases from Postgres, or seed defaults on fallback."""
    try:
        pool = _get_pool()
        try:
            connection_context = pool.connection(timeout=1)
        except TypeError:
            connection_context = pool.connection()

        with connection_context as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT normalized_name, display_name, city_name, country_name
                    FROM place_aliases
                    ORDER BY normalized_name
                    """
                )
                rows = cursor.fetchall()
    except Exception:
        return [dict(alias) for alias in _DEFAULT_PLACE_ALIASES]

    return [
        {
            "normalized_name": str(row[0]),
            "display_name": str(row[1]),
            "city_name": str(row[2]),
            "country_name": str(row[3]),
        }
        for row in rows
    ]


@lru_cache(maxsize=16)
def list_reference_values(category: str) -> list[str]:
    """Return display values for a reference-data category.

    For `cities` and `countries`, syncs from Country State City API on demand
    when the database category is empty. Other categories fall back to the
    local seed data if the database is unavailable.
    """
    normalized_category = str(category or "").strip().lower()
    if not normalized_category:
        return []

    fallback = [display_name for _, display_name, _ in _REFERENCE_SEED_DATA.get(normalized_category, [])]

    try:
        pool = _get_pool()
        try:
            connection_context = pool.connection(timeout=1)
        except TypeError:
            connection_context = pool.connection()

        with connection_context as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT display_name
                    FROM reference_options
                    WHERE category = %s
                    ORDER BY display_name
                    """,
                    (normalized_category,),
                )
                rows = cursor.fetchall()
    except Exception:
        return fallback

    values = [str(row[0]) for row in rows]
    if values:
        return values

    if normalized_category in {"cities", "countries"}:
        try:
            _sync_country_state_city_reference_options()
        except Exception as exc:
            logger.warning(
                "Country State City sync failed for category '%s': %s",
                normalized_category,
                exc,
            )
            return fallback

        try:
            pool = _get_pool()
            try:
                connection_context = pool.connection(timeout=1)
            except TypeError:
                connection_context = pool.connection()

            with connection_context as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT display_name
                        FROM reference_options
                        WHERE category = %s
                        ORDER BY display_name
                        """,
                        (normalized_category,),
                    )
                    rows = cursor.fetchall()
        except Exception:
            return fallback
        return [str(row[0]) for row in rows]

    return fallback


@lru_cache(maxsize=256)
def lookup_airport_code(city_name: str) -> str:
    """Resolve a city name to an airport code using DB-backed reference data."""
    normalized_name = _normalise_place_name(city_name)
    if not normalized_name:
        return ""

    fallback = CITY_TO_AIRPORT.get(city_name, "")
    if not fallback:
        for configured_city, airport_code in CITY_TO_AIRPORT.items():
            if _normalise_place_name(configured_city) == normalized_name:
                fallback = airport_code
                break

    try:
        pool = _get_pool()
        try:
            connection_context = pool.connection(timeout=1)
        except TypeError:
            connection_context = pool.connection()

        with connection_context as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT value_code
                    FROM reference_options
                    WHERE category = %s AND normalized_name = %s
                    """,
                    ("airport_cities", normalized_name),
                )
                row = cursor.fetchone()
    except Exception:
        return fallback

    if row is None:
        return fallback
    return str(row[0] or "").strip() or fallback


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
