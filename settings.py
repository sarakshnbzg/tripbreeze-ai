"""Environment-backed application settings and runtime defaults."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths
PROJECT_ROOT = Path(__file__).parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
CHROMA_ROOT_DIR = PROJECT_ROOT / "chroma_db"
EVALS_DIR = PROJECT_ROOT / "evals"
RAG_EVAL_DATASET_PATH = EVALS_DIR / "rag_eval_dataset.jsonl"
RAG_EVAL_OUTPUT_DIR = EVALS_DIR / "results"

_DEFAULT_FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]


class Settings(BaseSettings):
    """Typed runtime settings loaded from `.env` and the process environment."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    serpapi_api_key: str = Field("", alias="SERPAPI_API_KEY")
    memory_database_url: str = Field(
        "",
        validation_alias=AliasChoices("DATABASE_URL", "NEON_DATABASE_URL"),
    )
    csc_api_key: str = Field("", alias="CSC_API_KEY")
    require_persistent_checkpointer: bool = Field(False, alias="REQUIRE_PERSISTENT_CHECKPOINTER")

    smtp_host: str = Field("", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT", ge=1, le=65535)
    smtp_sender_email: str = Field("", alias="SMTP_SENDER_EMAIL")
    smtp_sender_password: str = Field("", alias="SMTP_SENDER_PASSWORD")
    smtp_use_tls: bool = Field(True, alias="SMTP_USE_TLS")

    openai_embedding_model: str = Field("text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")

    rag_chunk_size: int = Field(800, alias="RAG_CHUNK_SIZE", gt=0)
    rag_chunk_overlap: int = Field(100, alias="RAG_CHUNK_OVERLAP", ge=0)
    rag_top_k: int = Field(6, alias="RAG_TOP_K", gt=0)
    rag_vector_weight: float = 0.5
    rag_bm25_weight: float = 0.5
    rag_embedding_batch_size: int = Field(50, alias="RAG_EMBEDDING_BATCH_SIZE", gt=0)
    rag_embedding_max_retries: int = Field(4, alias="RAG_EMBEDDING_MAX_RETRIES", ge=0)

    max_flight_results: int = Field(5, alias="MAX_FLIGHT_RESULTS", gt=0)
    raw_flight_candidates: int = Field(15, alias="RAW_FLIGHT_CANDIDATES", gt=0)
    max_hotel_results: int = Field(5, alias="MAX_HOTEL_RESULTS", gt=0)
    default_currency: str = Field("EUR", alias="DEFAULT_CURRENCY")
    default_stay_nights: int = Field(7, alias="DEFAULT_STAY_NIGHTS", gt=0)
    default_daily_expense: float = Field(80.0, alias="DEFAULT_DAILY_EXPENSE", gt=0)

    langchain_tracing_v2: bool = Field(False, alias="LANGCHAIN_TRACING_V2")
    langchain_project: str = Field("tripbreeze-ai", alias="LANGCHAIN_PROJECT")
    langchain_api_key: str = Field("", alias="LANGCHAIN_API_KEY")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    app_env: str = Field("development", alias="APP_ENV")
    api_host: str = Field("127.0.0.1", alias="API_HOST")
    api_port: int = Field(8100, alias="API_PORT", ge=1, le=65535)
    api_base_url: str | None = Field(None, alias="API_BASE_URL")
    frontend_origins: list[str] = Field(default_factory=lambda: list(_DEFAULT_FRONTEND_ORIGINS), alias="FRONTEND_ORIGINS")
    session_secret: str = Field("tripbreeze-dev-secret-change-me", alias="SESSION_SECRET")
    session_cookie_name: str = Field("tripbreeze_session", alias="SESSION_COOKIE_NAME")
    session_max_age_seconds: int = Field(60 * 60 * 24 * 7, alias="SESSION_MAX_AGE_SECONDS", gt=0)
    session_idle_timeout_seconds: int = Field(60 * 60 * 24, alias="SESSION_IDLE_TIMEOUT_SECONDS", gt=0)
    session_cookie_secure: bool = Field(False, alias="SESSION_COOKIE_SECURE")
    session_cookie_samesite: str = Field("strict", alias="SESSION_COOKIE_SAMESITE")

    @field_validator("session_cookie_samesite")
    @classmethod
    def validate_session_cookie_samesite(cls, value: str, info) -> str:
        normalized = str(value or "strict").strip().lower()
        if normalized not in {"strict", "lax", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be 'strict', 'lax', or 'none'")
        if normalized == "none":
            secure = info.data.get("session_cookie_secure")
            if not secure:
                raise ValueError("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true")
        return normalized

    @field_validator("rag_chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, value: int, info) -> int:
        chunk_size = info.data.get("rag_chunk_size")
        if isinstance(chunk_size, int) and value >= chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        return value

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return str(value or "EUR").upper()

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return str(value or "INFO").upper()

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        normalized = str(value or "development").strip().lower()
        aliases = {
            "dev": "development",
            "prod": "production",
        }
        return aliases.get(normalized, normalized)

    @field_validator("session_secret")
    @classmethod
    def validate_session_secret(cls, value: str, info) -> str:
        secret = str(value or "")
        app_env = str(info.data.get("app_env") or "development").strip().lower()
        if app_env in {"production", "staging"}:
            if secret == "tripbreeze-dev-secret-change-me":
                raise ValueError("SESSION_SECRET must be changed before running in production or staging")
            if len(secret) < 32:
                raise ValueError("SESSION_SECRET must be at least 32 characters in production or staging")
        return secret

    @field_validator("session_cookie_secure")
    @classmethod
    def validate_session_cookie_secure(cls, value: bool, info) -> bool:
        app_env = str(info.data.get("app_env") or "development").strip().lower()
        if app_env in {"production", "staging"} and not value:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production or staging")
        return value

    @field_validator("session_idle_timeout_seconds")
    @classmethod
    def validate_session_idle_timeout(cls, value: int, info) -> int:
        max_age = int(info.data.get("session_max_age_seconds") or 0)
        if max_age and value > max_age:
            raise ValueError("SESSION_IDLE_TIMEOUT_SECONDS must not exceed SESSION_MAX_AGE_SECONDS")
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value: object) -> list[str]:
        if value is None or value == "":
            return list(_DEFAULT_FRONTEND_ORIGINS)
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError("FRONTEND_ORIGINS must be a comma-separated string or list of strings")

    @property
    def embedding_models(self) -> dict[str, str]:
        return {
            "openai": self.openai_embedding_model,
        }

    @property
    def resolved_api_base_url(self) -> str:
        return self.api_base_url or f"http://{self.api_host}:{self.api_port}"


settings = Settings()

if settings.langchain_tracing_v2 and settings.langchain_api_key:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)

# Backward-compatible module-level exports
OPENAI_API_KEY = settings.openai_api_key
SERPAPI_API_KEY = settings.serpapi_api_key
MEMORY_DATABASE_URL = settings.memory_database_url
CSC_API_KEY = settings.csc_api_key
REQUIRE_PERSISTENT_CHECKPOINTER = settings.require_persistent_checkpointer

SMTP_HOST = settings.smtp_host
SMTP_PORT = settings.smtp_port
SMTP_SENDER_EMAIL = settings.smtp_sender_email
SMTP_SENDER_PASSWORD = settings.smtp_sender_password
SMTP_USE_TLS = settings.smtp_use_tls

EMBEDDING_MODELS = settings.embedding_models

RAG_CHUNK_SIZE = settings.rag_chunk_size
RAG_CHUNK_OVERLAP = settings.rag_chunk_overlap
RAG_TOP_K = settings.rag_top_k
RAG_VECTOR_WEIGHT = settings.rag_vector_weight
RAG_BM25_WEIGHT = settings.rag_bm25_weight
RAG_EMBEDDING_BATCH_SIZE = settings.rag_embedding_batch_size
RAG_EMBEDDING_MAX_RETRIES = settings.rag_embedding_max_retries

MAX_FLIGHT_RESULTS = settings.max_flight_results
RAW_FLIGHT_CANDIDATES = settings.raw_flight_candidates
MAX_HOTEL_RESULTS = settings.max_hotel_results
DEFAULT_CURRENCY = settings.default_currency
DEFAULT_STAY_NIGHTS = settings.default_stay_nights
DEFAULT_DAILY_EXPENSE = settings.default_daily_expense

LANGCHAIN_TRACING_V2 = settings.langchain_tracing_v2
LANGCHAIN_PROJECT = settings.langchain_project
LANGCHAIN_API_KEY = settings.langchain_api_key

LOG_LEVEL = settings.log_level
APP_ENV = settings.app_env
API_HOST = settings.api_host
API_PORT = settings.api_port
API_BASE_URL = settings.resolved_api_base_url
FRONTEND_ORIGINS = settings.frontend_origins
SESSION_SECRET = settings.session_secret
SESSION_COOKIE_NAME = settings.session_cookie_name
SESSION_MAX_AGE_SECONDS = settings.session_max_age_seconds
SESSION_IDLE_TIMEOUT_SECONDS = settings.session_idle_timeout_seconds
SESSION_COOKIE_SECURE = settings.session_cookie_secure
SESSION_COOKIE_SAMESITE = settings.session_cookie_samesite
