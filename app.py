"""FastAPI entry point for TripBreeze.

Run locally with:

    uv run python app.py

or:

    uv run uvicorn app:app --host 127.0.0.1 --port 8100
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

# Ensure project root is on the Python path so layered imports work.
sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: F401
from infrastructure.logging_utils import configure_logging
from presentation.api import app

configure_logging()


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="warning",
    )
