"""Factory helpers for creating chat and embedding models from user-selected providers."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from model_catalog import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    GOOGLE_MODELS,
    MODEL_COSTS,
    OPENAI_MODELS,
)
from settings import EMBEDDING_MODELS, GOOGLE_API_KEY, OPENAI_API_KEY
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

def get_available_models(provider: str) -> list[str]:
    """Return the supported model ids for a provider."""
    if provider == "google":
        return GOOGLE_MODELS
    return OPENAI_MODELS


def normalise_llm_selection(provider: str | None, model: str | None) -> tuple[str, str]:
    """Normalise provider/model selection against supported defaults."""
    chosen_provider = (provider or DEFAULT_LLM_PROVIDER).lower()
    if chosen_provider not in {"openai", "google"}:
        chosen_provider = DEFAULT_LLM_PROVIDER

    available_models = get_available_models(chosen_provider)
    chosen_model = model or DEFAULT_LLM_MODEL[chosen_provider]
    if chosen_model not in available_models:
        chosen_model = available_models[0]

    return chosen_provider, chosen_model


def get_provider_status(provider: str) -> tuple[bool, str]:
    """Return whether a provider is ready, plus a user-facing status message."""
    if provider == "google":
        if importlib.util.find_spec("langchain_google_genai") is None:
            return (
                False,
                "Google Gemini support requires the `langchain-google-genai` package. "
                "Install dependencies with `uv sync`.",
            )
        if not GOOGLE_API_KEY:
            return (
                False,
                "Google Gemini support requires `GOOGLE_API_KEY` or `GEMINI_API_KEY` in your environment or Streamlit secrets.",
            )
        return True, ""

    if not OPENAI_API_KEY:
        return False, "OpenAI support requires `OPENAI_API_KEY` in your environment or Streamlit secrets."

    return True, ""


def create_chat_model(
    provider: str | None = None,
    model: str | None = None,
    *,
    temperature: float = 0,
    **kwargs: Any,
):
    """Create a LangChain chat model for the selected provider."""
    chosen_provider, chosen_model = normalise_llm_selection(provider, model)
    logger.info(
        "Creating chat model provider=%s model=%s temperature=%s",
        chosen_provider,
        chosen_model,
        temperature,
    )

    if chosen_provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError(
                "Google Gemini support requires the `langchain-google-genai` package. "
                "Install it with `pip install langchain-google-genai`."
            ) from exc

        if not GOOGLE_API_KEY:
            logger.error("Google model requested but GOOGLE_API_KEY is not configured")
            raise RuntimeError(
                "Google Gemini support requires GOOGLE_API_KEY or GEMINI_API_KEY in your environment."
            )

        return ChatGoogleGenerativeAI(
            model=chosen_model,
            temperature=temperature,
            google_api_key=GOOGLE_API_KEY,
            **kwargs,
        )

    if not OPENAI_API_KEY:
        logger.error("OpenAI model requested but OPENAI_API_KEY is not configured")
        raise RuntimeError("OpenAI support requires OPENAI_API_KEY in your environment.")

    return ChatOpenAI(model=chosen_model, temperature=temperature, **kwargs)


def extract_token_usage(response, *, model: str, node: str) -> dict:
    """Extract token counts and cost from a LangChain AIMessage response."""
    usage = getattr(response, "usage_metadata", None) or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    costs = MODEL_COSTS.get(model, {})
    cost = (
        input_tokens * costs.get("input", 0)
        + output_tokens * costs.get("output", 0)
    )
    return {
        "node": node,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    }


_RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError)

try:
    from openai import APITimeoutError, RateLimitError, APIConnectionError, InternalServerError

    _RETRYABLE_EXCEPTIONS += (APITimeoutError, RateLimitError, APIConnectionError, InternalServerError)
except ImportError:
    pass

try:
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, DeadlineExceeded

    _RETRYABLE_EXCEPTIONS += (ResourceExhausted, ServiceUnavailable, DeadlineExceeded)
except ImportError:
    pass


def invoke_with_retry(llm, prompt, *, max_attempts: int = 3):
    """Invoke an LLM with automatic retry on transient failures.

    Retries up to *max_attempts* times with exponential back-off (1s, 2s, 4s …)
    on rate-limit, timeout, and server errors from OpenAI / Google.
    """

    @retry(
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        before_sleep=before_sleep_log(logger, 30),  # logging.WARNING
        reraise=True,
    )
    def _call():
        return llm.invoke(prompt)

    return _call()


def stream_with_retry(llm, prompt, *, max_attempts: int = 3) -> Iterator[Any]:
    """Stream LLM chunks with retry on startup failures.

    Once streaming has begun, yielded chunks are passed through directly.
    """

    @retry(
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        before_sleep=before_sleep_log(logger, 30),  # logging.WARNING
        reraise=True,
    )
    def _start_stream():
        return llm.stream(prompt)

    return _start_stream()


def create_embeddings(provider: str | None = None):
    """Create embeddings for the selected provider."""
    chosen_provider, _ = normalise_llm_selection(provider, None)
    logger.info("Creating embeddings provider=%s", chosen_provider)

    if chosen_provider == "google":
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError as exc:
            raise RuntimeError(
                "Google embeddings require the `langchain-google-genai` package. "
                "Install it with `pip install langchain-google-genai`."
            ) from exc

        if not GOOGLE_API_KEY:
            logger.error("Google embeddings requested but GOOGLE_API_KEY is not configured")
            raise RuntimeError(
                "Google embeddings require GOOGLE_API_KEY or GEMINI_API_KEY in your environment."
            )

        return GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODELS["google"],
            google_api_key=GOOGLE_API_KEY,
        )

    if not OPENAI_API_KEY:
        logger.error("OpenAI embeddings requested but OPENAI_API_KEY is not configured")
        raise RuntimeError("OpenAI embeddings require OPENAI_API_KEY in your environment.")

    return OpenAIEmbeddings(model=EMBEDDING_MODELS["openai"])
