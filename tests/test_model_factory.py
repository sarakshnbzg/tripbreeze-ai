"""Tests for infrastructure/llms/model_factory.py."""

from unittest.mock import MagicMock

import pytest

from infrastructure.llms.model_factory import (
    get_available_models,
    normalise_llm_selection,
    get_provider_status,
    extract_token_usage,
    invoke_with_retry,
    stream_with_retry,
    OPENAI_MODELS,
)


# ── get_available_models ──


class TestGetAvailableModels:
    def test_openai_models(self):
        assert get_available_models("openai") == OPENAI_MODELS

    def test_unknown_defaults_to_openai(self):
        assert get_available_models("unknown") == OPENAI_MODELS

    def test_google_aliases_to_openai_models(self):
        assert get_available_models("google") == OPENAI_MODELS


# ── normalise_llm_selection ──


class TestNormaliseLlmSelection:
    def test_valid_openai_selection(self):
        provider, model = normalise_llm_selection("openai", "gpt-4o-mini")
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    def test_google_provider_falls_back_to_openai(self):
        provider, model = normalise_llm_selection("google", "gemini-2.5-flash")
        assert provider == "openai"
        assert model == OPENAI_MODELS[0]

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

    def test_google_invalid_model_defaults_to_openai(self):
        provider, model = normalise_llm_selection("google", "bad-model")
        assert provider == "openai"
        assert model == OPENAI_MODELS[0]


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

    def test_google_status_uses_openai_requirements(self, monkeypatch):
        monkeypatch.setattr("infrastructure.llms.model_factory.OPENAI_API_KEY", "")
        ready, msg = get_provider_status("google")
        assert ready is False
        assert "OPENAI_API_KEY" in msg


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

    def test_exposes_cost_usd_alias(self):
        response = MagicMock()
        response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        result = extract_token_usage(response, model="gpt-4o-mini", node="test")
        assert result["cost_usd"] == result["cost"]


class TestInvokeWithRetry:
    def test_logs_completed_call_with_usage_and_latency(self, monkeypatch):
        class FakeOpenAIModel:
            model_name = "gpt-4o-mini"

            def invoke(self, prompt):
                return MagicMock(usage_metadata={"input_tokens": 12, "output_tokens": 3})

        llm = FakeOpenAIModel()

        events = []
        monkeypatch.setattr(
            "infrastructure.llms.model_factory.log_event",
            lambda logger, event, **fields: events.append((event, fields)),
        )

        invoke_with_retry(llm, "hello")

        assert events
        event, fields = events[-1]
        assert event == "llm.call_completed"
        assert fields["provider"] == "openai"
        assert fields["model"] == "gpt-4o-mini"
        assert fields["input_tokens"] == 12
        assert fields["output_tokens"] == 3
        assert "latency_ms" in fields
        assert fields["attempts"] == 1

    def test_logs_retry_before_success(self, monkeypatch):
        class FakeOpenAIModel:
            model_name = "gpt-4o-mini"

            def __init__(self):
                self.calls = 0

            def invoke(self, prompt):
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutError("boom")
                return MagicMock(usage_metadata={"input_tokens": 12, "output_tokens": 3})

        llm = FakeOpenAIModel()

        events = []
        monkeypatch.setattr(
            "infrastructure.llms.model_factory.log_event",
            lambda logger, event, **fields: events.append((event, fields)),
        )
        monkeypatch.setattr("infrastructure.llms.model_factory.time.sleep", lambda seconds: None)

        invoke_with_retry(llm, "hello", max_attempts=3)

        assert events[0][0] == "llm.call_retrying"
        assert events[-1][0] == "llm.call_completed"
        assert events[-1][1]["attempts"] == 2

    def test_logs_failed_call(self, monkeypatch):
        class FakeOpenAIModel:
            model_name = "gpt-4o-mini"

            def invoke(self, prompt):
                raise TimeoutError("boom")

        llm = FakeOpenAIModel()

        events = []
        monkeypatch.setattr(
            "infrastructure.llms.model_factory.log_event",
            lambda logger, event, **fields: events.append((event, fields)),
        )

        with pytest.raises(TimeoutError):
            invoke_with_retry(llm, "hello", max_attempts=1)

        assert events[-1][0] == "llm.call_failed"
        assert events[-1][1]["error_type"] == "TimeoutError"
        assert events[-1][1]["attempts"] == 1


class TestStreamWithRetry:
    def test_logs_completed_stream(self, monkeypatch):
        final_chunk = MagicMock(usage_metadata={"input_tokens": 7, "output_tokens": 2})

        class FakeOpenAIModel:
            model_name = "gpt-4o-mini"

            def stream(self, prompt):
                return iter([MagicMock(), final_chunk])

        llm = FakeOpenAIModel()

        events = []
        monkeypatch.setattr(
            "infrastructure.llms.model_factory.log_event",
            lambda logger, event, **fields: events.append((event, fields)),
        )

        chunks = list(stream_with_retry(llm, "hello"))

        assert len(chunks) == 2
        assert events[-1][0] == "llm.stream_completed"
        assert events[-1][1]["input_tokens"] == 7
        assert events[-1][1]["output_tokens"] == 2
        assert events[-1][1]["attempts"] == 1
