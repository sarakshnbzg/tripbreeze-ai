"""Entry point — bootstraps config, starts the FastAPI backend in a background
thread, then launches the Streamlit UI.

Run with:  streamlit run app.py
"""

import sys
import threading
from pathlib import Path

# Ensure project root is on the Python path so layered imports work.
sys.path.insert(0, str(Path(__file__).parent))

# Trigger config loading (env vars, paths)
import config  # noqa: F401

from infrastructure.logging_utils import configure_logging

configure_logging()

# Start the FastAPI backend on a background daemon thread so it lives
# inside the same process as Streamlit and dies when the process exits.
import uvicorn
import streamlit as st
from presentation.api import app as fastapi_app


@st.cache_resource
def start_backend():
    """Start the FastAPI backend once and cache it across Streamlit reruns."""
    threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": fastapi_app,
            "host": "127.0.0.1",
            "port": 8100,
            "log_level": "warning",
        },
        daemon=True,
    ).start()


start_backend()

from presentation.streamlit_app import main

main()
