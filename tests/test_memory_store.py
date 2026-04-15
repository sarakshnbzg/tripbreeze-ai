"""Tests for infrastructure/persistence/memory_store.py."""

import json

import pytest

from infrastructure.persistence.memory_store import (
    _DEFAULT_PROFILE,
    _sanitise_user_id,
    list_profiles,
    load_profile,
    register_user,
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


class TestLoadSaveProfile:
    def test_load_missing_profile_returns_defaults(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        profile = load_profile("new_user")

        assert profile["user_id"] == "new_user"
        assert profile["travel_class"] == "ECONOMY"
        assert profile["past_trips"] == []
        for key in _DEFAULT_PROFILE:
            assert key in profile

    def test_save_and_load_roundtrip(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("test_user", {"home_city": "Berlin", "travel_class": "BUSINESS"})
        profile = load_profile("test_user")

        assert profile["home_city"] == "Berlin"
        assert profile["travel_class"] == "BUSINESS"
        assert profile["user_id"] == "test_user"
        assert profile["preferred_airlines"] == []

    def test_save_overwrites_existing(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("u1", {"home_city": "London"})
        save_profile("u1", {"home_city": "Paris"})
        profile = load_profile("u1")

        assert profile["home_city"] == "Paris"

    def test_save_invalid_id_raises(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        with pytest.raises(ValueError, match="Invalid profile ID"):
            save_profile("../bad", {})


class TestListProfiles:
    def test_empty_returns_empty(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        assert list_profiles() == []

    def test_lists_saved_profiles(self, monkeypatch):
        fake_connection = FakeConnection()
        monkeypatch.setattr("infrastructure.persistence.memory_store._get_pool", lambda: FakePool(fake_connection))

        save_profile("alice", {})
        save_profile("bob", {})

        assert list_profiles() == ["alice", "bob"]


class TestUpdateProfileFromTrip:
    def test_adds_destination_to_past_trips(self, monkeypatch):
        fake_connection = FakeConnection()
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
