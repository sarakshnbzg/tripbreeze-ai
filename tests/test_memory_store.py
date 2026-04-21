"""Tests for infrastructure/persistence/memory_store.py."""

import json

import pytest

from infrastructure.persistence.memory_store import (
    _DEFAULT_PROFILE,
    _normalise_place_name,
    _sanitise_user_id,
    list_place_aliases,
    list_reference_values,
    load_destination_daily_expense,
    lookup_airport_code,
    load_place_country,
    load_profile,
    register_user,
    save_place_alias,
    save_profile,
    update_profile_from_trip,
    verify_user,
)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._results = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        params = params or ()
        normalised = " ".join(query.split())
        self.connection.queries.append((normalised, params))

        if "CREATE TABLE IF NOT EXISTS profiles" in normalised:
            self._results = []
            return

        if "CREATE TABLE IF NOT EXISTS place_aliases" in normalised:
            self._results = []
            return

        if "CREATE TABLE IF NOT EXISTS destination_daily_expenses" in normalised:
            self._results = []
            return

        if "CREATE TABLE IF NOT EXISTS reference_options" in normalised:
            self._results = []
            return

        if normalised.startswith("SELECT profile_json FROM profiles WHERE user_id = %s"):
            user_id = params[0]
            payload = self.connection.rows.get(user_id)
            self._results = [] if payload is None else [(payload,)]
            return

        if normalised.startswith("SELECT user_id FROM profiles ORDER BY user_id"):
            self._results = [(user_id,) for user_id in sorted(self.connection.rows)]
            return

        if normalised.startswith("INSERT INTO profiles"):
            user_id, payload = params
            self.connection.rows[user_id] = json.loads(payload)
            self._results = []
            return

        if normalised.startswith("SELECT country_name FROM place_aliases WHERE normalized_name = %s"):
            normalized_name = params[0]
            payload = self.connection.place_aliases.get(normalized_name)
            self._results = [] if payload is None else [(payload["country_name"],)]
            return

        if normalised.startswith("SELECT normalized_name, display_name, city_name, country_name FROM place_aliases ORDER BY normalized_name"):
            self._results = [
                (
                    normalized_name,
                    payload["display_name"],
                    payload["city_name"],
                    payload["country_name"],
                )
                for normalized_name, payload in sorted(self.connection.place_aliases.items())
            ]
            return

        if normalised.startswith("INSERT INTO place_aliases"):
            normalized_name, display_name, city_name, country_name, source = params
            self.connection.place_aliases[normalized_name] = {
                "display_name": display_name,
                "city_name": city_name,
                "country_name": country_name,
                "source": source,
            }
            self._results = []
            return

        if (
            normalised.startswith("SELECT normalized_name, daily_expense_eur FROM destination_daily_expenses WHERE normalized_name = %s")
        ):
            normalized_name = params[0]
            payload = self.connection.destination_daily_expenses.get(normalized_name)
            self._results = [] if payload is None else [(normalized_name, payload["daily_expense_eur"])]
            return

        if normalised.startswith("SELECT normalized_name, daily_expense_eur FROM destination_daily_expenses ORDER BY normalized_name"):
            self._results = [
                (normalized_name, payload["daily_expense_eur"])
                for normalized_name, payload in sorted(self.connection.destination_daily_expenses.items())
            ]
            return

        if normalised.startswith("INSERT INTO destination_daily_expenses"):
            normalized_name, display_name, daily_expense_eur, source = params
            self.connection.destination_daily_expenses.setdefault(
                normalized_name,
                {
                    "display_name": display_name,
                    "daily_expense_eur": float(daily_expense_eur),
                    "source": source,
                },
            )
            if "DO UPDATE SET" in normalised:
                self.connection.destination_daily_expenses[normalized_name] = {
                    "display_name": display_name,
                    "daily_expense_eur": float(daily_expense_eur),
                    "source": source,
                }
            self._results = []
            return

        if normalised.startswith("SELECT display_name FROM reference_options WHERE category = %s ORDER BY display_name"):
            category = params[0]
            self._results = [
                (payload["display_name"],)
                for (stored_category, _normalized_name), payload in sorted(self.connection.reference_options.items())
                if stored_category == category
            ]
            return

        if normalised.startswith("SELECT value_code FROM reference_options WHERE category = %s AND normalized_name = %s"):
            category, normalized_name = params
            payload = self.connection.reference_options.get((category, normalized_name))
            self._results = [] if payload is None else [(payload["value_code"],)]
            return

        if normalised.startswith("INSERT INTO reference_options"):
            category, normalized_name, display_name, value_code, source = params
            self.connection.reference_options.setdefault(
                (category, normalized_name),
                {
                    "display_name": display_name,
                    "value_code": value_code,
                    "source": source,
                },
            )
            self._results = []
            return

        if normalised.startswith("SELECT 1 FROM user_credentials WHERE user_id = %s"):
            user_id = params[0]
            self._results = [(1,)] if user_id in self.connection.credentials else []
            return

        if normalised.startswith("SELECT password_hash, salt FROM user_credentials WHERE user_id = %s"):
            user_id = params[0]
            payload = self.connection.credentials.get(user_id)
            self._results = [] if payload is None else [(payload["password_hash"], payload["salt"])]
            return

        if normalised.startswith("INSERT INTO user_credentials"):
            user_id, password_hash, salt = params
            self.connection.credentials[user_id] = {
                "password_hash": password_hash,
                "salt": salt,
            }
            self._results = []
            return

        raise AssertionError(f"Unexpected query: {normalised}")

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)


class FakeConnection:
    def __init__(self):
        self.rows = {}
        self.credentials = {}
        self.place_aliases = {}
        self.destination_daily_expenses = {}
        self.reference_options = {}
        self.queries = []
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commit_count += 1


class FakePool:
    """Mimics psycopg_pool.ConnectionPool using a single FakeConnection."""

    def __init__(self, fake_connection):
        self._conn = fake_connection

    def connection(self):
        return self._conn


class TestSanitiseUserId:
    def test_valid_alphanumeric(self):
        assert _sanitise_user_id("alice") == "alice"

    def test_valid_with_hyphens_underscores(self):
        assert _sanitise_user_id("user-1_test") == "user-1_test"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            _sanitise_user_id("")

    def test_path_traversal_raises(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            _sanitise_user_id("../../etc/passwd")

    def test_dots_rejected(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            _sanitise_user_id("user.name")

    def test_slashes_rejected(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            _sanitise_user_id("user/name")

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match="Invalid profile ID"):
            _sanitise_user_id("user name")


class TestNormalisePlaceName:
    def test_normalises_case_and_commas(self):
        assert _normalise_place_name(" New York, USA ") == "new york usa"


class TestLoadSaveProfile:
    def test_load_missing_profile_returns_defaults(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        profile = load_profile("new_user")

        assert profile["user_id"] == "new_user"
        assert profile["travel_class"] == "ECONOMY"
        assert profile["past_trips"] == []
        for key in _DEFAULT_PROFILE:
            assert key in profile

    def test_save_and_load_roundtrip(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("test_user", {"home_city": "Berlin", "travel_class": "BUSINESS"})
        profile = load_profile("test_user")

        assert profile["home_city"] == "Berlin"
        assert profile["travel_class"] == "BUSINESS"
        assert profile["user_id"] == "test_user"
        assert profile["preferred_airlines"] == []

    def test_save_overwrites_existing(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {"home_city": "London"})
        save_profile("u1", {"home_city": "Paris"})
        profile = load_profile("u1")

        assert profile["home_city"] == "Paris"

    def test_save_invalid_id_raises(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        with pytest.raises(ValueError, match="Invalid profile ID"):
            save_profile("../bad", {})

class TestUpdateProfileFromTrip:
    def test_adds_destination_to_past_trips(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {})
        trip = {"destination": "Tokyo", "departure_date": "2026-07-01", "return_date": "2026-07-10"}
        profile = update_profile_from_trip("u1", trip)

        assert len(profile["past_trips"]) == 1
        assert profile["past_trips"][0]["destination"] == "Tokyo"

    def test_past_trips_capped_at_ten(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        existing = [{"destination": f"City{i}", "dates": ""} for i in range(10)]
        save_profile("u1", {"past_trips": existing})
        profile = update_profile_from_trip("u1", {"destination": "New"})

        assert len(profile["past_trips"]) == 10
        assert profile["past_trips"][-1]["destination"] == "New"

    def test_sets_home_city_only_if_empty(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {"home_city": ""})
        profile = update_profile_from_trip("u1", {"destination": "Paris", "home_city": "London"})

        assert profile["home_city"] == "London"

    def test_does_not_overwrite_existing_home_city(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {"home_city": "Berlin"})
        profile = update_profile_from_trip("u1", {"destination": "Paris", "home_city": "London"})

        assert profile["home_city"] == "Berlin"

    def test_updates_travel_class(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {})
        profile = update_profile_from_trip("u1", {"destination": "Paris", "travel_class": "BUSINESS"})

        assert profile["travel_class"] == "BUSINESS"

    def test_no_destination_skips_past_trips(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {"past_trips": []})
        profile = update_profile_from_trip("u1", {"destination": "", "travel_class": "FIRST"})

        assert profile["past_trips"] == []
        assert profile["travel_class"] == "FIRST"


class TestAuthentication:
    def test_register_user_stores_bcrypt_hash(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        created = register_user("secure_user", "long-password")

        assert created is True
        stored = fake_connection.credentials["secure_user"]
        assert stored["salt"] == ""
        assert stored["password_hash"].startswith("$2")
        assert verify_user("secure_user", "long-password") is True

    def test_register_user_persists_initial_profile(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        created = register_user(
            "secure_user",
            "long-password",
            {"home_city": "Berlin", "passport_country": "Germany", "preferred_airlines": ["Lufthansa"]},
        )

        assert created is True
        profile = load_profile("secure_user")
        assert profile["home_city"] == "Berlin"
        assert profile["passport_country"] == "Germany"
        assert profile["preferred_airlines"] == ["Lufthansa"]

    def test_register_user_rejects_short_password(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        with pytest.raises(ValueError, match="at least 8 characters"):
            register_user("secure_user", "short")

    def test_verify_user_rejects_wrong_password(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))
        register_user("secure_user", "long-password")

        assert verify_user("secure_user", "wrong-password") is False

    def test_verify_user_rejects_non_bcrypt_stored_hash(self, monkeypatch):
        fake_connection = FakeConnection()
        fake_connection.credentials["legacy_user"] = {
            "password_hash": "not-a-bcrypt-hash",
            "salt": "pepper",
        }
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        assert verify_user("legacy_user", "long-password") is False


class TestPlaceAliases:
    def test_save_and_load_place_alias_roundtrip(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_place_alias("Marrakesh", country_name="Morocco", source="geocoder")

        assert load_place_country("Marrakesh") == "Morocco"
        assert fake_connection.place_aliases["marrakesh"]["source"] == "geocoder"

    def test_load_place_country_returns_empty_when_missing(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        assert load_place_country("Unknown City") == ""

    def test_list_place_aliases_returns_saved_aliases(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_place_alias("Marrakesh", country_name="Morocco", source="geocoder")

        aliases = list_place_aliases()
        assert aliases == [
            {
                "normalized_name": "marrakesh",
                "display_name": "Marrakesh",
                "city_name": "Marrakesh",
                "country_name": "Morocco",
            }
        ]


class TestDestinationDailyExpenses:
    def test_load_destination_daily_expense_matches_substring(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        fake_connection.destination_daily_expenses["paris"] = {
            "display_name": "Paris",
            "daily_expense_eur": 110.0,
            "source": "seed",
        }
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        rate, source_key = load_destination_daily_expense("Paris, France")
        assert rate == 110.0
        assert source_key == "paris"

    def test_load_destination_daily_expense_returns_none_when_missing(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        rate, source_key = load_destination_daily_expense("Unknown City")
        assert rate is None
        assert source_key == ""


class TestReferenceOptions:
    def test_list_reference_values_reads_db_backed_options(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        fake_connection.reference_options[("cities", "berlin")] = {
            "display_name": "Berlin",
            "value_code": None,
            "source": "manual",
        }
        fake_connection.reference_options[("cities", "paris")] = {
            "display_name": "Paris",
            "value_code": None,
            "source": "manual",
        }
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        assert list_reference_values("cities") == ["Berlin", "Paris"]

    def test_list_reference_values_syncs_cities_from_csc_when_empty(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))
        monkeypatch.setattr(
            "infrastructure.persistence.memory_store._sync_country_state_city_reference_options",
            lambda: fake_connection.reference_options.update(
                {
                    ("cities", "berlin"): {
                        "display_name": "Berlin",
                        "value_code": None,
                        "source": "csc",
                    },
                    ("cities", "paris"): {
                        "display_name": "Paris",
                        "value_code": None,
                        "source": "csc",
                    },
                }
            ),
        )

        assert list_reference_values("cities") == ["Berlin", "Paris"]

    def test_list_reference_values_syncs_countries_from_csc_when_empty(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))
        monkeypatch.setattr(
            "infrastructure.persistence.memory_store._sync_country_state_city_reference_options",
            lambda: fake_connection.reference_options.update(
                {
                    ("countries", "france"): {
                        "display_name": "France",
                        "value_code": "FR",
                        "source": "csc",
                    },
                    ("countries", "germany"): {
                        "display_name": "Germany",
                        "value_code": "DE",
                        "source": "csc",
                    },
                }
            ),
        )

        assert list_reference_values("countries") == ["France", "Germany"]

    def test_lookup_airport_code_reads_db_backed_mapping(self, monkeypatch):
        fake_connection = FakeConnection()
        list_reference_values.cache_clear()
        lookup_airport_code.cache_clear()
        fake_connection.reference_options[("airport_cities", "berlin")] = {
            "display_name": "Berlin",
            "value_code": "BER",
            "source": "manual",
        }
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        assert lookup_airport_code("Berlin") == "BER"
