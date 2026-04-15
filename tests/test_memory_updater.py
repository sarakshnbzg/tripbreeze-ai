"""Tests for domain/nodes/memory_updater.py."""

from unittest.mock import patch

from domain.nodes.memory_updater import memory_updater


class TestMemoryUpdater:
    def test_updates_profile_from_trip(self):
        fake_profile = {"user_id": "alice", "past_trips": [{"destination": "Paris"}]}

        with patch(
            "domain.nodes.memory_updater.update_profile_from_trip",
            return_value=fake_profile,
        ) as mock_update:
            result = memory_updater({
                "user_id": "alice",
                "trip_request": {
                    "destination": "Paris",
                    "departure_date": "2026-07-01",
                    "return_date": "2026-07-08",
                    "origin": "London",
                    "travel_class": "ECONOMY",
                },
                "user_profile": {"passport_country": "UK"},
            })

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] == "alice"
        trip_data = call_args[0][1]
        assert trip_data["destination"] == "Paris from London"
        assert trip_data["passport_country"] == "UK"

        assert result["user_profile"] == fake_profile
        assert result["current_step"] == "done"

    def test_uses_multi_city_history_label(self):
        with patch(
            "domain.nodes.memory_updater.update_profile_from_trip",
            return_value={"past_trips": []},
        ) as mock_update:
            memory_updater({
                "user_id": "alice",
                "trip_request": {
                    "destination": "Paris",
                    "departure_date": "2026-07-01",
                    "return_date": "2026-07-08",
                    "origin": "Berlin",
                    "travel_class": "ECONOMY",
                },
                "trip_legs": [
                    {"origin": "Berlin", "destination": "Paris"},
                    {"origin": "Paris", "destination": "Barcelona"},
                    {"origin": "Barcelona", "destination": "Berlin"},
                ],
                "user_profile": {"passport_country": "Germany"},
            })

        trip_data = mock_update.call_args[0][1]
        assert trip_data["destination"] == "Paris -> Barcelona from Berlin"

    def test_uses_open_jaw_multi_city_history_label(self):
        with patch(
            "domain.nodes.memory_updater.update_profile_from_trip",
            return_value={"past_trips": []},
        ) as mock_update:
            memory_updater({
                "user_id": "alice",
                "trip_request": {
                    "destination": "Paris",
                    "departure_date": "2026-07-01",
                    "return_date": "2026-07-05",
                    "origin": "Berlin",
                    "travel_class": "ECONOMY",
                },
                "trip_legs": [
                    {"origin": "Berlin", "destination": "Paris"},
                    {"origin": "Paris", "destination": "Barcelona"},
                ],
                "user_profile": {"passport_country": "Germany"},
            })

        trip_data = mock_update.call_args[0][1]
        assert trip_data["destination"] == "Paris -> Barcelona from Berlin"

    def test_skips_when_no_trip_request(self):
        result = memory_updater({"user_id": "alice", "trip_request": {}})
        assert result["current_step"] == "done"
        assert "user_profile" not in result

    def test_default_user_id(self):
        with patch(
            "domain.nodes.memory_updater.update_profile_from_trip",
            return_value={},
        ) as mock_update:
            memory_updater({"trip_request": {"destination": "Rome"}})
            assert mock_update.call_args[0][0] == "default_user"

    def test_system_message_included(self):
        with patch(
            "domain.nodes.memory_updater.update_profile_from_trip",
            return_value={"past_trips": []},
        ):
            result = memory_updater({
                "user_id": "u1",
                "trip_request": {"destination": "Tokyo"},
                "user_profile": {},
            })
            assert result["messages"][0]["role"] == "system"
            assert "updated" in result["messages"][0]["content"].lower()
