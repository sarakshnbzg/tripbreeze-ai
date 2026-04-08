"""Centralised configuration — single source of truth for all settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
CHROMA_ROOT_DIR = PROJECT_ROOT / "chroma_db"

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

# Model settings
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = {
    "openai": "gpt-4o-mini",
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
DEFAULT_DAILY_EXPENSE = 80.0  # EUR baseline — used as fallback
DAILY_EXPENSE_BY_CURRENCY: dict[str, float] = {
    "EUR": 80.0,
    "USD": 85.0,
    "GBP": 70.0,
    "CAD": 115.0,
    "AUD": 130.0,
    "JPY": 12000.0,
    "CHF": 100.0,
    "SGD": 115.0,
    "AED": 310.0,
    "NZD": 140.0,
}

# LangSmith tracing
LANGCHAIN_TRACING_V2 = _get_config_value("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_PROJECT = _get_config_value("LANGCHAIN_PROJECT", "tripbreeze-ai")
LANGCHAIN_API_KEY = _get_config_value("LANGCHAIN_API_KEY", "")

if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", LANGCHAIN_PROJECT)
    os.environ.setdefault("LANGCHAIN_API_KEY", LANGCHAIN_API_KEY)

# Profile options
CITIES = [
    "", "Atlanta", "Los Angeles", "Chicago", "Dallas", "Denver", "New York",
    "San Francisco", "Seattle", "Las Vegas", "Orlando", "Miami", "Charlotte",
    "Phoenix", "Houston", "Boston", "Minneapolis", "Detroit", "Philadelphia",
    "Washington D.C.", "Austin", "Honolulu", "San Diego", "Tampa",
    "London", "Paris", "Frankfurt", "Amsterdam", "Madrid", "Barcelona",
    "Rome", "Munich", "Zurich", "Istanbul", "Berlin", "Vienna", "Lisbon",
    "Prague", "Athens", "Budapest", "Copenhagen", "Dublin", "Edinburgh",
    "Reykjavik", "Dubai", "Doha", "Singapore",
    "Tokyo", "Seoul", "Hong Kong", "Bangkok", "Delhi", "Mumbai",
    "Bali", "Kyoto", "Osaka", "Phuket",
    "Sydney", "Melbourne", "Auckland",
    "Sao Paulo", "Rio de Janeiro", "Mexico City", "Cancun",
    "Bogota", "Lima", "Santiago", "Buenos Aires", "Havana",
    "Toronto", "Vancouver", "Montreal",
    "Cape Town", "Johannesburg", "Cairo", "Nairobi", "Marrakech",
    "Florence", "Santorini", "Maldives",
]

COUNTRIES = [
    "", "United States", "United Kingdom", "Canada", "Australia", "Germany",
    "France", "Spain", "Italy", "Netherlands", "Switzerland", "Austria",
    "Belgium", "Sweden", "Norway", "Denmark", "Finland", "Ireland", "Portugal",
    "Japan", "South Korea", "China", "India", "Singapore", "Thailand",
    "Malaysia", "Indonesia", "Philippines", "Vietnam", "Taiwan",
    "Brazil", "Mexico", "Argentina", "Colombia", "Chile", "Peru",
    "South Africa", "Kenya", "Egypt", "Nigeria", "Morocco",
    "United Arab Emirates", "Qatar", "Saudi Arabia", "Turkey", "Israel",
    "New Zealand", "Greece", "Poland", "Czech Republic", "Hungary", "Romania",
    "Iran",
    "Russia", "Ukraine",
]

AIRLINES = [
    "Delta", "United", "American", "Southwest", "JetBlue", "Alaska", "Spirit",
    "Frontier", "Hawaiian", "British Airways", "Lufthansa", "Air France", "KLM",
    "Iberia", "Swiss", "Austrian", "SAS", "Finnair", "TAP Portugal",
    "Turkish Airlines", "Emirates", "Qatar Airways", "Etihad", "Saudia",
    "Singapore Airlines", "Cathay Pacific", "ANA", "JAL", "Korean Air",
    "Asiana", "Thai Airways", "Air India", "Qantas", "Air New Zealand",
    "LATAM", "Avianca", "Air Canada", "WestJet",
    "Ryanair", "EasyJet", "Vueling", "Norwegian",
]

DESTINATIONS = [
    "", "Paris", "London", "Tokyo", "New York", "Rome", "Barcelona", "Dubai",
    "Bangkok", "Istanbul", "Singapore", "Amsterdam", "Prague", "Sydney",
    "Lisbon", "Berlin", "Vienna", "Seoul", "Hong Kong", "Bali", "Cancun",
    "Cape Town", "Marrakech", "Buenos Aires", "Rio de Janeiro", "Lima",
    "Mexico City", "Toronto", "Vancouver", "Reykjavik", "Athens",
    "Budapest", "Copenhagen", "Dublin", "Edinburgh", "Florence",
    "Havana", "Kyoto", "Maldives", "Miami", "Montreal", "Munich",
    "Nairobi", "Osaka", "Phuket", "San Francisco", "Santorini",
    "Zurich",
]

CITY_TO_AIRPORT: dict[str, str] = {
    # North America
    "Atlanta": "ATL", "Los Angeles": "LAX", "Chicago": "ORD", "Dallas": "DFW",
    "Denver": "DEN", "New York": "JFK", "San Francisco": "SFO", "Seattle": "SEA",
    "Las Vegas": "LAS", "Orlando": "MCO", "Miami": "MIA", "Charlotte": "CLT",
    "Phoenix": "PHX", "Houston": "IAH", "Boston": "BOS", "Minneapolis": "MSP",
    "Detroit": "DTW", "Philadelphia": "PHL", "Washington D.C.": "DCA",
    "Austin": "AUS", "Honolulu": "HNL", "San Diego": "SAN", "Tampa": "TPA",
    "Toronto": "YYZ", "Vancouver": "YVR", "Montreal": "YUL",
    "Mexico City": "MEX", "Cancun": "CUN", "Havana": "HAV",
    # Europe
    "London": "LHR", "Paris": "CDG", "Frankfurt": "FRA", "Amsterdam": "AMS",
    "Madrid": "MAD", "Barcelona": "BCN", "Rome": "FCO", "Munich": "MUC",
    "Zurich": "ZRH", "Istanbul": "IST", "Lisbon": "LIS", "Berlin": "BER",
    "Vienna": "VIE", "Prague": "PRG", "Athens": "ATH", "Budapest": "BUD",
    "Copenhagen": "CPH", "Dublin": "DUB", "Edinburgh": "EDI", "Florence": "FLR",
    "Reykjavik": "KEF", "Santorini": "JTR",
    # Middle East
    "Dubai": "DXB", "Doha": "DOH",
    # Asia
    "Singapore": "SIN", "Tokyo": "NRT", "Seoul": "ICN", "Hong Kong": "HKG",
    "Bangkok": "BKK", "Delhi": "DEL", "Mumbai": "BOM", "Bali": "DPS",
    "Kyoto": "KIX", "Osaka": "KIX", "Phuket": "HKT",
    # Oceania
    "Sydney": "SYD", "Melbourne": "MEL", "Auckland": "AKL",
    # South America
    "Sao Paulo": "GRU", "Bogota": "BOG", "Lima": "LIM", "Santiago": "SCL",
    "Buenos Aires": "EZE", "Rio de Janeiro": "GIG",
    # Africa
    "Cape Town": "CPT", "Johannesburg": "JNB", "Cairo": "CAI",
    "Nairobi": "NBO", "Marrakech": "RAK", "Maldives": "MLE",
}

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
