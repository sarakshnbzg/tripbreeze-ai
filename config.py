"""Centralised configuration — single source of truth for all settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
CHROMA_ROOT_DIR = PROJECT_ROOT / "chroma_db"
EVALS_DIR = PROJECT_ROOT / "evals"
RAG_EVAL_DATASET_PATH = EVALS_DIR / "rag_eval_dataset.jsonl"
RAG_EVAL_OUTPUT_DIR = EVALS_DIR / "results"

# Environment
load_dotenv(PROJECT_ROOT / ".env")


def _get_config_value(name: str, default: str = "") -> str:
    """Read configuration from env vars first, then Streamlit secrets if available."""
    env_value = os.getenv(name)
    if env_value:
        return env_value

    try:
        import streamlit as st

        if name in st.secrets:
            value = st.secrets[name]
            return str(value) if value is not None else default
    except Exception:
        pass

    return default

OPENAI_API_KEY = _get_config_value("OPENAI_API_KEY", "")
GOOGLE_API_KEY = _get_config_value("GOOGLE_API_KEY", "") or _get_config_value("GEMINI_API_KEY", "")
SERPAPI_API_KEY = _get_config_value("SERPAPI_API_KEY", "")
MEMORY_DATABASE_URL = _get_config_value("DATABASE_URL", "") or _get_config_value("NEON_DATABASE_URL", "")
CSC_API_KEY = _get_config_value("CSC_API_KEY", "")
REQUIRE_PERSISTENT_CHECKPOINTER = _get_config_value("REQUIRE_PERSISTENT_CHECKPOINTER", "false").lower() == "true"

# Email / SMTP settings
SMTP_HOST = _get_config_value("SMTP_HOST", "")
SMTP_PORT = int(_get_config_value("SMTP_PORT", "587"))
SMTP_SENDER_EMAIL = _get_config_value("SMTP_SENDER_EMAIL", "")
SMTP_SENDER_PASSWORD = _get_config_value("SMTP_SENDER_PASSWORD", "")
SMTP_USE_TLS = _get_config_value("SMTP_USE_TLS", "true").lower() == "true"

# Model settings
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = {
    "openai": "gpt-4o-mini",
    "google": "gemini-2.5-flash",
}
DEFAULT_JUDGE_MODEL = {
    "openai": "gpt-4.1-mini",
    "google": "gemini-2.5-flash",
}
EMBEDDING_MODELS = {
    "openai": _get_config_value("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "google": _get_config_value("GOOGLE_EMBEDDING_MODEL", "gemini-embedding-001"),
}

# RAG settings
RAG_CHUNK_SIZE = 800
RAG_CHUNK_OVERLAP = 100
RAG_TOP_K = 6
RAG_VECTOR_WEIGHT = 0.5
RAG_BM25_WEIGHT = 0.5
RAG_EMBEDDING_BATCH_SIZE = int(_get_config_value("RAG_EMBEDDING_BATCH_SIZE", "50"))
RAG_GOOGLE_EMBEDDING_BATCH_DELAY_SECONDS = float(
    _get_config_value("RAG_GOOGLE_EMBEDDING_BATCH_DELAY_SECONDS", "31")
)
RAG_EMBEDDING_MAX_RETRIES = int(_get_config_value("RAG_EMBEDDING_MAX_RETRIES", "4"))

# Search settings
MAX_FLIGHT_RESULTS = 5
RAW_FLIGHT_CANDIDATES = 15
MAX_HOTEL_RESULTS = 5
DEFAULT_CURRENCY = "EUR"
DEFAULT_STAY_NIGHTS = 7  # assumed hotel stay when no return/check-out date is given for a one-way trip
DEFAULT_DAILY_EXPENSE = 80.0  # EUR baseline — used as fallback

# LangSmith tracing
LANGCHAIN_TRACING_V2 = _get_config_value("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_PROJECT = _get_config_value("LANGCHAIN_PROJECT", "tripbreeze-ai")
LANGCHAIN_API_KEY = _get_config_value("LANGCHAIN_API_KEY", "")

if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", LANGCHAIN_PROJECT)
    os.environ.setdefault("LANGCHAIN_API_KEY", LANGCHAIN_API_KEY)

CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SGD", "AED", "NZD"]

HOTEL_STARS = [3, 4, 5, 2, 1]

TRAVEL_CLASSES = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"]

# Model costs (USD per token)
MODEL_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4.1-mini": {"input": 0.40 / 1_000_000, "output": 1.60 / 1_000_000},
    "gpt-4.1-nano": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    "gpt-3.5-turbo": {"input": 0.50 / 1_000_000, "output": 1.50 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gemini-2.5-flash-lite": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
}

# Logging
LOG_LEVEL = _get_config_value("LOG_LEVEL", "INFO").upper()

# Runtime / server settings
STREAMLIT_HOST = _get_config_value("STREAMLIT_HOST", "0.0.0.0")
STREAMLIT_PORT = int(_get_config_value("STREAMLIT_PORT", "8501"))
API_HOST = _get_config_value("API_HOST", "127.0.0.1")
API_PORT = int(_get_config_value("API_PORT", "8100"))
API_BASE_URL = _get_config_value("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")
