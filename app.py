"""Entry point — thin wrapper that bootstraps config and launches the UI.

Run with:  streamlit run app.py
"""

import sys
from pathlib import Path

# Ensure project root is on the Python path so layered imports work.
sys.path.insert(0, str(Path(__file__).parent))

# Trigger config loading (env vars, paths)
import config  # noqa: F401

from infrastructure.logging_utils import configure_logging
from presentation.streamlit_app import main


configure_logging()
main()
