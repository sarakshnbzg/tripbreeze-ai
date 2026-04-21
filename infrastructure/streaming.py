"""Thread-local helpers for forwarding live streaming updates to the API layer."""

from __future__ import annotations

from contextlib import contextmanager
from threading import local
from typing import Callable, Iterator

_state = local()


def get_token_emitter() -> Callable[[str], None] | None:
    """Return the active token emitter for the current worker thread, if any."""
    return getattr(_state, "token_emitter", None)


@contextmanager
def token_emitter_context(emitter: Callable[[str], None] | None) -> Iterator[None]:
    """Temporarily register a token emitter for the current worker thread."""
    previous = get_token_emitter()
    _state.token_emitter = emitter
    try:
        yield
    finally:
        if previous is None:
            if hasattr(_state, "token_emitter"):
                delattr(_state, "token_emitter")
        else:
            _state.token_emitter = previous
