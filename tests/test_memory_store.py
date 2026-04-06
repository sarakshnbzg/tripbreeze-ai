"""Tests for infrastructure/persistence/memory_store.py."""

import json

import pytest

from infrastructure.persistence.memory_store import (
    _sanitise_user_id,
    load_profile,
    save_profile,
    list_profiles,
    update_profile_from_trip,
    _DEFAULT_PROFILE,
)


# ── _sanitise_user_id ──


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


# ── load_profile / save_profile ──


class TestLoadSaveProfile:
    def test_load_missing_profile_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        profile = load_profile("new_user")
        assert profile["user_id"] == "new_user"
        assert profile["travel_class"] == "ECONOMY"
        assert profile["past_trips"] == []
        for key in _DEFAULT_PROFILE:
            assert key in profile

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("test_user", {"home_city": "Berlin", "travel_class": "BUSINESS"})
        profile = load_profile("test_user")
        assert profile["home_city"] == "Berlin"
        assert profile["travel_class"] == "BUSINESS"
        assert profile["user_id"] == "test_user"
        # Defaults should be merged in
        assert profile["preferred_airlines"] == []

    def test_save_overwrites_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("u1", {"home_city": "London"})
        save_profile("u1", {"home_city": "Paris"})
        profile = load_profile("u1")
        assert profile["home_city"] == "Paris"

    def test_save_invalid_id_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        with pytest.raises(ValueError, match="Invalid profile ID"):
            save_profile("../bad", {})


# ── list_profiles ──


class TestListProfiles:
    def test_empty_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        assert list_profiles() == []

    def test_lists_saved_profiles(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        (tmp_path / "alice.json").write_text("{}")
        (tmp_path / "bob.json").write_text("{}")
        assert list_profiles() == ["alice", "bob"]

    def test_ignores_non_json_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        (tmp_path / "alice.json").write_text("{}")
        (tmp_path / "notes.txt").write_text("hi")
        assert list_profiles() == ["alice"]


# ── update_profile_from_trip ──


class TestUpdateProfileFromTrip:
    def test_adds_destination_to_past_trips(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("u1", {})
        trip = {"destination": "Tokyo", "departure_date": "2026-07-01", "return_date": "2026-07-10"}
        profile = update_profile_from_trip("u1", trip)
        assert len(profile["past_trips"]) == 1
        assert profile["past_trips"][0]["destination"] == "Tokyo"

    def test_past_trips_capped_at_ten(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        existing = [{"destination": f"City{i}", "dates": ""} for i in range(10)]
        save_profile("u1", {"past_trips": existing})
        trip = {"destination": "New"}
        profile = update_profile_from_trip("u1", trip)
        assert len(profile["past_trips"]) == 10
        assert profile["past_trips"][-1]["destination"] == "New"

    def test_sets_home_city_only_if_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("u1", {"home_city": ""})
        trip = {"destination": "Paris", "home_city": "London"}
        profile = update_profile_from_trip("u1", trip)
        assert profile["home_city"] == "London"

    def test_does_not_overwrite_existing_home_city(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("u1", {"home_city": "Berlin"})
        trip = {"destination": "Paris", "home_city": "London"}
        profile = update_profile_from_trip("u1", trip)
        assert profile["home_city"] == "Berlin"

    def test_updates_travel_class(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("u1", {})
        trip = {"destination": "Paris", "travel_class": "BUSINESS"}
        profile = update_profile_from_trip("u1", trip)
        assert profile["travel_class"] == "BUSINESS"

    def test_no_destination_skips_past_trips(self, tmp_path, monkeypatch):
        monkeypatch.setattr("infrastructure.persistence.memory_store.MEMORY_DIR", tmp_path)
        save_profile("u1", {"past_trips": []})
        trip = {"destination": "", "travel_class": "FIRST"}
        profile = update_profile_from_trip("u1", trip)
        assert profile["past_trips"] == []
        assert profile["travel_class"] == "FIRST"
