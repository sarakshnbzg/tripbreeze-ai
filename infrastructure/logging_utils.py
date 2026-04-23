"""Shared logging helpers for consistent app-wide observability."""

from __future__ import annotations

import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from config import LOG_LEVEL

_JSON_FIELDS = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once for the application process."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level or LOG_LEVEL)
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter(
            fmt=_JSON_FIELDS,
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
        )
    )

    root_logger.setLevel(level or LOG_LEVEL)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger after ensuring logging is configured."""
    configure_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured log entry with a stable event name and optional fields."""
    logger.info(event, extra={"event": event, **fields})
