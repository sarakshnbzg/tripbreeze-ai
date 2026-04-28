"""Shared API security helpers for rate limiting, payload guards, and safe errors."""

from __future__ import annotations

import json
import time
from collections import deque
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request

from infrastructure.logging_utils import get_logger, log_event

logger = get_logger(__name__)

_RATE_LIMIT_ATTEMPTS: dict[tuple[str, str], deque[float]] = {}
_RATE_LIMIT_LOCK = Lock()


def _client_address(request: Request) -> str:
    headers = getattr(request, "headers", {}) or {}
    forwarded_for = headers.get("x-forwarded-for", "")
    if forwarded_for.strip():
        return forwarded_for.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", "")
    return str(host or "unknown")


def _request_actor(request: Request) -> str:
    authenticated_user = str(getattr(request.state, "authenticated_user", "")).strip()
    if authenticated_user:
        return f"user:{authenticated_user}"
    return f"ip:{_client_address(request)}"


def enforce_rate_limit(
    bucket: str,
    request: Request,
    *,
    max_attempts: int,
    window_seconds: int,
    message: str,
) -> None:
    """Apply a lightweight in-process rate limit for an endpoint bucket."""
    now = time.monotonic()
    key = (bucket, _request_actor(request))
    with _RATE_LIMIT_LOCK:
        attempts = _RATE_LIMIT_ATTEMPTS.setdefault(key, deque())
        while attempts and now - attempts[0] > window_seconds:
            attempts.popleft()
        if len(attempts) >= max_attempts:
            log_event(
                logger,
                "api.rate_limit_exceeded",
                bucket=bucket,
                actor=key[1],
                max_attempts=max_attempts,
                window_seconds=window_seconds,
                path=str(request.url.path),
            )
            raise HTTPException(status_code=429, detail=message)
        attempts.append(now)


def enforce_content_length(request: Request, *, max_bytes: int, message: str) -> None:
    """Reject oversized requests when Content-Length is available."""
    headers = getattr(request, "headers", {}) or {}
    header_value = str(headers.get("content-length", "")).strip()
    if not header_value:
        return
    try:
        content_length = int(header_value)
    except ValueError:
        return
    if content_length > max_bytes:
        log_event(
            logger,
            "api.request_too_large",
            path=str(getattr(getattr(request, "url", None), "path", "")),
            content_length=content_length,
            max_bytes=max_bytes,
        )
        raise HTTPException(status_code=413, detail=message)


def enforce_text_length(field_name: str, value: str | None, *, max_chars: int, message: str) -> None:
    """Reject overly large text fields."""
    if value is None:
        return
    if len(str(value)) > max_chars:
        raise HTTPException(status_code=413, detail=message)


def enforce_json_size(field_name: str, payload: Any, *, max_chars: int, message: str) -> None:
    """Reject overly large structured payloads."""
    if payload is None:
        return
    serialised = json.dumps(payload, default=str)
    if len(serialised) > max_chars:
        raise HTTPException(status_code=413, detail=message)


def log_and_raise_api_error(
    *,
    event: str,
    public_message: str,
    exc: Exception,
    status_code: int = 500,
    **fields: Any,
) -> None:
    """Log a structured API error and raise a safe HTTPException."""
    log_event(
        logger,
        event,
        error_type=type(exc).__name__,
        error=str(exc),
        **fields,
    )
    logger.exception("%s", event)
    raise HTTPException(status_code=status_code, detail=public_message) from exc
