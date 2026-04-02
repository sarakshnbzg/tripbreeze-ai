"""Shared logging helpers for consistent app-wide observability."""

from __future__ import annotations

import logging

from config import LOG_LEVEL

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once for the application process."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level or LOG_LEVEL)
        return

    logging.basicConfig(
        level=level or LOG_LEVEL,
        format=_LOG_FORMAT,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a module logger after ensuring logging is configured."""
    configure_logging()
    return logging.getLogger(name)
