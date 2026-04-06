"""Tests for domain/nodes/profile_loader.py."""

from unittest.mock import patch

from domain.nodes.profile_loader import profile_loader


class TestProfileLoader:
    def test_loads_profile_and_returns_state(self):
        fake_profile = {
            "user_id": "alice",
            "home_city": "Berlin",
            "travel_class": "BUSINESS",
            "preferred_hotel_stars": [4, 5],
            "passport_country": "Germany",
            "past_trips": [{"destination": "Tokyo"}],
        }

        with patch("domain.nodes.profile_loader.load_profile", return_value=fake_profile):
            result = profile_loader({"user_id": "alice"})

        assert result["user_profile"] == fake_profile
        assert result["current_step"] == "profile_loaded"
        msg = result["messages"][0]
        assert msg["role"] == "system"
        assert "Berlin" in msg["content"]
        assert "BUSINESS" in msg["content"]
        assert "Germany" in msg["content"]
        assert "Tokyo" in msg["content"]

    def test_default_user_id(self):
        with patch("domain.nodes.profile_loader.load_profile") as mock_load:
            mock_load.return_value = {"user_id": "default_user"}
            profile_loader({})
            mock_load.assert_called_with("default_user")

    def test_empty_profile_shows_not_set(self):
        empty_profile = {
            "user_id": "new",
            "home_city": "",
            "travel_class": "ECONOMY",
            "preferred_hotel_stars": [],
            "passport_country": "",
            "past_trips": [],
        }

        with patch("domain.nodes.profile_loader.load_profile", return_value=empty_profile):
            result = profile_loader({"user_id": "new"})

        msg = result["messages"][0]["content"]
        assert "not set" in msg
        assert "none" in msg
