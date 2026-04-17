"""Helpers for replaying recorded LLM responses in golden-prompt tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


_GOLDEN_DIR = Path(__file__).resolve().parent / "golden_prompts"


def load_golden_cases(filename: str) -> list[dict[str, Any]]:
    """Load a list of golden test cases from tests/golden_prompts."""
    path = _GOLDEN_DIR / filename
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)

    if not isinstance(cases, list):
        raise ValueError(f"Golden cases in {path} must be a list.")
    return cases


def build_recorded_response(payload: dict[str, Any]) -> SimpleNamespace:
    """Create a lightweight AI-message stand-in from recorded JSON."""
    return SimpleNamespace(
        content=payload.get("content", ""),
        tool_calls=payload.get("tool_calls", []),
        usage_metadata=payload.get(
            "usage_metadata",
            {"input_tokens": 0, "output_tokens": 0},
        ),
    )


def stringify_prompt(prompt_or_messages: Any) -> str:
    """Convert a string or LangChain message list into plain text for assertions."""
    if isinstance(prompt_or_messages, str):
        return prompt_or_messages
    if isinstance(prompt_or_messages, list):
        parts = []
        for message in prompt_or_messages:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                parts.append(content)
            else:
                parts.append(str(content))
        return "\n\n".join(parts)
    return str(prompt_or_messages)
