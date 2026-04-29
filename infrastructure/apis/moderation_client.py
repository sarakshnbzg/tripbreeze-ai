"""OpenAI Moderations API helpers for user and generated text checks."""

from __future__ import annotations

import json
from typing import Any

from infrastructure.logging_utils import get_logger, log_event
from settings import (
    MODERATION_ENABLED,
    MODERATION_FAIL_CLOSED,
    MODERATION_MODEL,
    MODERATION_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
)

logger = get_logger(__name__)


class ModerationBlockedError(ValueError):
    """Raised when text is flagged by the moderation provider."""

    def __init__(self, *, context: str, categories: list[str]):
        self.context = context
        self.categories = categories
        super().__init__("Content blocked by safety policy.")


class ModerationUnavailableError(RuntimeError):
    """Raised when moderation is configured to fail closed and the check fails."""


def _stringify_payload(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    return json.dumps(payload, ensure_ascii=False, default=str)


def _flagged_categories(result: Any) -> list[str]:
    categories = getattr(result, "categories", None)
    if not categories:
        return []
    if hasattr(categories, "model_dump"):
        category_map = categories.model_dump()
    elif isinstance(categories, dict):
        category_map = categories
    else:
        category_map = vars(categories)
    return sorted(str(name) for name, flagged in category_map.items() if flagged)


def _moderate_with_openai(*, text: str, context: str) -> tuple[bool, list[str]]:
    import openai

    client = openai.OpenAI(api_key=OPENAI_API_KEY, timeout=MODERATION_TIMEOUT_SECONDS)
    response = client.moderations.create(
        model=MODERATION_MODEL,
        input=text,
    )
    result = response.results[0] if getattr(response, "results", None) else None
    flagged = bool(getattr(result, "flagged", False)) if result is not None else False
    categories = _flagged_categories(result)
    log_event(
        logger,
        "moderation.checked",
        context=context,
        flagged=flagged,
        categories=categories,
        model=MODERATION_MODEL,
    )
    return flagged, categories


def check_text_allowed(payload: Any, *, context: str) -> bool:
    """Return whether payload passes moderation.

    Moderation provider failures fail open by default so optional safety checks
    do not break demos or local development unless MODERATION_FAIL_CLOSED=true.
    """
    text = _stringify_payload(payload)
    if not text or not MODERATION_ENABLED or not OPENAI_API_KEY:
        return True

    try:
        flagged, categories = _moderate_with_openai(text=text, context=context)
        if flagged:
            raise ModerationBlockedError(context=context, categories=categories)
        return True
    except ModerationBlockedError:
        raise
    except Exception as exc:
        log_event(
            logger,
            "moderation.failed",
            context=context,
            error_type=type(exc).__name__,
            model=MODERATION_MODEL,
            fail_closed=MODERATION_FAIL_CLOSED,
        )
        logger.warning("Moderation check failed for %s: %s", context, exc)
        if MODERATION_FAIL_CLOSED:
            raise ModerationUnavailableError("Moderation check unavailable.") from exc
        return True


def assert_text_allowed(payload: Any, *, context: str) -> None:
    """Raise when payload should not continue through the app."""
    check_text_allowed(payload, context=context)
