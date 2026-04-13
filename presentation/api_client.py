"""HTTP client — thin wrapper for Streamlit to call the FastAPI backend.

All graph interaction goes through these functions instead of importing
application/domain modules directly.
"""

import json
from typing import Any, Generator

import httpx

from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

API_BASE = "http://127.0.0.1:8100"

# Generous timeout: planning can take minutes (multiple LLM + API calls).
_STREAM_TIMEOUT = httpx.Timeout(timeout=300.0, connect=10.0)
_REQUEST_TIMEOUT = httpx.Timeout(timeout=120.0, connect=10.0)


def _parse_sse_lines(lines_iter) -> Generator[tuple[str, dict], None, None]:
    """Parse raw SSE text lines into (event_type, data_dict) tuples."""
    event_type = "message"
    data_buf = ""
    for raw_line in lines_iter:
        line = raw_line.strip()
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_buf = line[len("data:"):].strip()
        elif line == "":
            # Empty line = end of event
            if data_buf:
                try:
                    parsed = json.loads(data_buf)
                except json.JSONDecodeError:
                    parsed = {"raw": data_buf}
                yield event_type, parsed
            event_type = "message"
            data_buf = ""


def transcribe_audio(audio_bytes: bytes, filename: str = "recording.wav") -> str:
    """POST audio to /api/transcribe, return transcribed text."""
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        resp = client.post(
            f"{API_BASE}/api/transcribe",
            files={"file": (filename, audio_bytes)},
        )
        resp.raise_for_status()
        return resp.json()["text"]


def stream_search(request: dict[str, Any]) -> Generator[tuple[str, dict], None, None]:
    """POST to /api/search, yield parsed SSE events as (event_type, data) tuples."""
    with httpx.Client(timeout=_STREAM_TIMEOUT) as client:
        with client.stream("POST", f"{API_BASE}/api/search", json=request) as resp:
            resp.raise_for_status()
            yield from _parse_sse_lines(resp.iter_lines())


def get_state(thread_id: str) -> dict:
    """GET the current graph state for a thread."""
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        resp = client.get(f"{API_BASE}/api/search/{thread_id}/state")
        resp.raise_for_status()
        return resp.json()


def fetch_return_flights(thread_id: str, params: dict[str, Any]) -> list[dict]:
    """POST to /api/search/{thread_id}/return-flights."""
    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        resp = client.post(
            f"{API_BASE}/api/search/{thread_id}/return-flights",
            json=params,
        )
        resp.raise_for_status()
        return resp.json()


def stream_approve(thread_id: str, request: dict[str, Any]) -> Generator[tuple[str, dict], None, None]:
    """POST to /api/search/{thread_id}/approve, yield parsed SSE events."""
    with httpx.Client(timeout=_STREAM_TIMEOUT) as client:
        with client.stream(
            "POST",
            f"{API_BASE}/api/search/{thread_id}/approve",
            json=request,
        ) as resp:
            resp.raise_for_status()
            yield from _parse_sse_lines(resp.iter_lines())
