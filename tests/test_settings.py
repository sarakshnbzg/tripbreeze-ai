"""Tests for runtime settings validation."""

import pytest

from settings import Settings


class TestSettingsSecurity:
    def test_production_requires_non_default_session_secret(self):
        with pytest.raises(ValueError, match="SESSION_SECRET must be changed"):
            Settings(
                APP_ENV="production",
                SESSION_SECRET="tripbreeze-dev-secret-change-me",
                SESSION_COOKIE_SECURE=True,
            )

    def test_production_requires_long_session_secret(self):
        with pytest.raises(ValueError, match="at least 32 characters"):
            Settings(
                APP_ENV="production",
                SESSION_SECRET="too-short",
                SESSION_COOKIE_SECURE=True,
            )

    def test_production_requires_secure_session_cookie(self):
        with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE must be true"):
            Settings(
                APP_ENV="production",
                SESSION_SECRET="a" * 32,
                SESSION_COOKIE_SECURE=False,
            )

    def test_idle_timeout_must_not_exceed_max_age(self):
        with pytest.raises(ValueError, match="must not exceed"):
            Settings(
                SESSION_MAX_AGE_SECONDS=60,
                SESSION_IDLE_TIMEOUT_SECONDS=120,
            )
