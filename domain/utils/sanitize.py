"""Prompt injection defence for untrusted user text."""

import html
import re

from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"^\s*(system|assistant|developer|tool)\s*:", re.IGNORECASE),
    re.compile(r"^\s*ignore\s+(all\s+)?previous\s+instructions\b", re.IGNORECASE),
    re.compile(r"^\s*disregard\s+(all\s+)?previous\s+instructions\b", re.IGNORECASE),
    re.compile(r"^\s*forget\s+(all\s+)?previous\s+instructions\b", re.IGNORECASE),
    re.compile(r"^\s*you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"^\s*act\s+as\b", re.IGNORECASE),
)


def sanitise_untrusted_text(text: str, *, context: str = "") -> str:
    """Strip prompt-injection directives and HTML-escape untrusted user text."""
    if not text:
        return ""

    retained_lines: list[str] = []
    stripped_lines = 0
    for line in text.replace("\r\n", "\n").split("\n"):
        if any(pattern.search(line) for pattern in _PROMPT_INJECTION_PATTERNS):
            stripped_lines += 1
            continue
        retained_lines.append(line)

    sanitised = html.escape("\n".join(retained_lines).strip(), quote=False)
    if stripped_lines:
        logger.info(
            "Removed suspicious prompt-like lines context=%s count=%s",
            context or "unknown",
            stripped_lines,
        )
    return sanitised
