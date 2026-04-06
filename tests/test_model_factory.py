"""Tests for infrastructure/llms/model_factory.py."""

from unittest.mock import MagicMock

import pytest

from infrastructure.llms.model_factory import (
    get_available_models,
    normalise_llm_selection,
    get_provider_status,
    extract_token_usage,
    OPENAI_MODELS,
    GOOGLE_MODELS,
)


# ── get_available_models ──


class TestGetAvailableModels:
    def test_openai_models(self):
        assert get_available_models("openai") == OPENAI_MODELS

    def test_google_models(self):
        assert get_available_models("google") == GOOGLE_MODELS

    def test_unknown_defaults_to_openai(self):
        assert get_available_models("unknown") == OPENAI_MODELS


# ── normalise_llm_selection ──


class TestNormaliseLlmSelection:
    def test_valid_openai_selection(self):
        provider, model = normalise_llm_selection("openai", "gpt-4o-mini")
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    def test_valid_google_selection(self):
        provider, model = normalise_llm_selection("google", "gemini-2.5-flash")
        assert provider == "google"
        assert model == "gemini-2.5-flash"

    def test_none_provider_defaults(self):
        provider, model = normalise_llm_selection(None, None)
        assert provider == "openai"
        assert model in OPENAI_MODELS

    def test_invalid_provider_defaults_to_openai(self):
        provider, model = normalise_llm_selection("azure", None)
        assert provider == "openai"

    def test_invalid_model_defaults_to_first(self):
        provider, model = normalise_llm_selection("openai", "nonexistent-model")
        assert model == OPENAI_MODELS[0]

    def test_case_insensitive_provider(self):
        provider, model = normalise_llm_selection("OPENAI", None)
        assert provider == "openai"

    def test_google_invalid_model_defaults(self):
        provider, model = normalise_llm_selection("google", "bad-model")
        assert provider == "google"
        assert model == GOOGLE_MODELS[0]


# ── get_provider_status ──


class TestGetProviderStatus:
    def test_openai_without_key(self, monkeypatch):
        monkeypatch.setattr("infrastructure.llms.model_factory.OPENAI_API_KEY", "")
        ready, msg = get_provider_status("openai")
        assert ready is False
        assert "OPENAI_API_KEY" in msg

    def test_openai_with_key(self, monkeypatch):
        monkeypatch.setattr("infrastructure.llms.model_factory.OPENAI_API_KEY", "sk-test")
        ready, msg = get_provider_status("openai")
        assert ready is True
        assert msg == ""

    def test_google_without_key(self, monkeypatch):
        monkeypatch.setattr("infrastructure.llms.model_factory.GOOGLE_API_KEY", "")
        ready, msg = get_provider_status("google")
        assert ready is False
        assert "GOOGLE_API_KEY" in msg or "package" in msg


# ── extract_token_usage ──


class TestExtractTokenUsage:
    def test_extracts_counts_and_cost(self):
        response = MagicMock()
        response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        result = extract_token_usage(response, model="gpt-4o-mini", node="test")
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["node"] == "test"
        assert result["model"] == "gpt-4o-mini"
        assert result["cost"] > 0

    def test_missing_usage_metadata(self):
        response = MagicMock(spec=[])  # no usage_metadata attribute
        result = extract_token_usage(response, model="gpt-4o-mini", node="test")
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["cost"] == 0

    def test_unknown_model_zero_cost(self):
        response = MagicMock()
        response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        result = extract_token_usage(response, model="unknown-model", node="test")
        assert result["cost"] == 0
