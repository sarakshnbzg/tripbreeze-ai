"""Shared pytest fixtures."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.golden_prompt_replay import build_recorded_response, stringify_prompt


@pytest.fixture(autouse=True)
def disable_moderation_network_calls(monkeypatch):
    """Keep tests from calling the live Moderations API unless they opt in."""
    monkeypatch.setattr("infrastructure.apis.moderation_client.MODERATION_ENABLED", False)


@pytest.fixture
def mock_llm_responses():
    """Patch a node's LLM boundary to replay recorded responses in order."""

    @contextmanager
    def _mock(module_name: str, responses: list[dict[str, Any]]):
        prompt_log: list[str] = []
        replay_index = 0

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm

        def _invoke(_bound_llm, prompt_or_messages):
            nonlocal replay_index
            if replay_index >= len(responses):
                raise AssertionError(
                    f"{module_name} made more LLM calls than recorded ({len(responses)})."
                )

            recorded = responses[replay_index]
            replay_index += 1

            prompt_text = stringify_prompt(prompt_or_messages)
            prompt_log.append(prompt_text)

            for fragment in recorded.get("expect_prompt_contains", []):
                assert fragment in prompt_text

            return build_recorded_response(recorded)

        def _extract_token_usage(_response, *, model: str, node: str):
            return {"node": node, "model": model}

        with (
            patch(f"{module_name}.create_chat_model", return_value=mock_llm),
            patch(f"{module_name}.invoke_with_retry", side_effect=_invoke),
            patch(f"{module_name}.extract_token_usage", side_effect=_extract_token_usage),
        ):
            yield prompt_log

        assert replay_index == len(responses), (
            f"{module_name} used {replay_index} recorded responses, "
            f"but {len(responses)} were provided."
        )

    return _mock
