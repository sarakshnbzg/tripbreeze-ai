"""Tests for OpenAI moderation helper behavior."""

from types import SimpleNamespace

import pytest

from infrastructure.apis import moderation_client
from infrastructure.apis.moderation_client import ModerationBlockedError, check_text_allowed


class TestModerationClient:
    def test_allows_empty_text_without_provider_call(self, monkeypatch):
        monkeypatch.setattr(moderation_client, "MODERATION_ENABLED", True)
        monkeypatch.setattr(moderation_client, "OPENAI_API_KEY", "test-key")

        assert check_text_allowed("   ", context="empty") is True

    def test_raises_with_categories_when_provider_flags_text(self, monkeypatch):
        class FakeModerations:
            def create(self, **kwargs):
                return SimpleNamespace(
                    results=[
                        SimpleNamespace(
                            flagged=True,
                            categories={"violence": True, "hate": False},
                        )
                    ]
                )

        class FakeOpenAIClient:
            moderations = FakeModerations()

        class FakeOpenAI:
            def OpenAI(self, **kwargs):
                return FakeOpenAIClient()

        monkeypatch.setattr(moderation_client, "MODERATION_ENABLED", True)
        monkeypatch.setattr(moderation_client, "OPENAI_API_KEY", "test-key")
        monkeypatch.setitem(__import__("sys").modules, "openai", FakeOpenAI())

        with pytest.raises(ModerationBlockedError) as exc_info:
            check_text_allowed("flagged", context="search")

        assert exc_info.value.categories == ["violence"]
