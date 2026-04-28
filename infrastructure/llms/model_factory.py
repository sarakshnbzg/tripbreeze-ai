"""Factory helpers for creating chat and embedding models from user-selected providers."""

from __future__ import annotations

import importlib.util
import time
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
    MODEL_COSTS,
    OPENAI_MODELS,
)
from settings import EMBEDDING_MODELS, OPENAI_API_KEY
from infrastructure.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def _infer_llm_metadata(llm: Any, *, _visited: set[int] | None = None) -> tuple[str, str]:
    """Best-effort provider/model lookup for raw and wrapped LangChain models."""
    if _visited is None:
        _visited = set()

    object_id = id(llm)
    if object_id in _visited:
        return normalise_llm_selection(None, None)
    _visited.add(object_id)

    provider = ""
    model = str(getattr(llm, "model_name", "") or getattr(llm, "model", "") or "").strip()

    class_name = llm.__class__.__name__.lower()
    module_name = llm.__class__.__module__.lower()
    if "openai" in class_name or "openai" in module_name:
        provider = "openai"

    if provider and model:
        return normalise_llm_selection(provider, model)

    stored_attrs = vars(llm) if hasattr(llm, "__dict__") else {}
    for attr in ("bound", "runnable", "llm"):
        nested = stored_attrs.get(attr)
        if nested is None or nested is llm:
            continue
        nested_provider, nested_model = _infer_llm_metadata(nested, _visited=_visited)
        if nested_provider and nested_model:
            return nested_provider, nested_model

    return normalise_llm_selection(provider or None, model or None)


def _usage_from_response(response: Any, *, model: str) -> dict[str, float | int]:
    """Extract token counts and estimated USD cost from a LangChain response."""
    usage = getattr(response, "usage_metadata", None) or {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    costs = MODEL_COSTS.get(model, {})
    cost_usd = (
        input_tokens * costs.get("input", 0)
        + output_tokens * costs.get("output", 0)
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }

def get_available_models(provider: str) -> list[str]:
    """Return the supported model ids for a provider."""
    return OPENAI_MODELS


def normalise_llm_selection(provider: str | None, model: str | None) -> tuple[str, str]:
    """Normalise provider/model selection against supported defaults."""
    chosen_provider = (provider or DEFAULT_LLM_PROVIDER).lower()
    if chosen_provider != "openai":
        chosen_provider = DEFAULT_LLM_PROVIDER

    available_models = get_available_models(chosen_provider)
    chosen_model = model or DEFAULT_LLM_MODEL[chosen_provider]
    if chosen_model not in available_models:
        chosen_model = available_models[0]

    return chosen_provider, chosen_model


def get_provider_status(provider: str) -> tuple[bool, str]:
    """Return whether a provider is ready, plus a user-facing status message."""
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

    if not OPENAI_API_KEY:
        logger.error("OpenAI model requested but OPENAI_API_KEY is not configured")
        raise RuntimeError("OpenAI support requires OPENAI_API_KEY in your environment.")

    return ChatOpenAI(model=chosen_model, temperature=temperature, **kwargs)


def extract_token_usage(response, *, model: str, node: str) -> dict:
    """Extract token counts and cost from a LangChain AIMessage response."""
    usage = _usage_from_response(response, model=model)
    return {
        "node": node,
        "model": model,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost": usage["cost_usd"],
        "cost_usd": usage["cost_usd"],
    }


_RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError)

try:
    from openai import APITimeoutError, RateLimitError, APIConnectionError, InternalServerError

    _RETRYABLE_EXCEPTIONS += (APITimeoutError, RateLimitError, APIConnectionError, InternalServerError)
except ImportError:
    pass

def invoke_with_retry(llm, prompt, *, max_attempts: int = 3):
    """Invoke an LLM with automatic retry on transient failures.

    Retries up to *max_attempts* times with exponential back-off (1s, 2s, 4s …)
    on rate-limit, timeout, and server errors from OpenAI.
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

    provider, model = _infer_llm_metadata(llm)
    started_at = time.perf_counter()
    try:
        response = _call()
    except Exception as exc:
        log_event(
            logger,
            "llm.call_failed",
            provider=provider,
            model=model,
            latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error_type=exc.__class__.__name__,
        )
        raise

    usage = _usage_from_response(response, model=model)
    log_event(
        logger,
        "llm.call_completed",
        provider=provider,
        model=model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=usage["cost_usd"],
        latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
    )
    return response


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

    provider, model = _infer_llm_metadata(llm)
    started_at = time.perf_counter()

    try:
        stream = _start_stream()
    except Exception as exc:
        log_event(
            logger,
            "llm.stream_failed",
            provider=provider,
            model=model,
            latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error_type=exc.__class__.__name__,
        )
        raise

    def _logged_stream() -> Iterator[Any]:
        last_chunk = None
        try:
            for chunk in stream:
                last_chunk = chunk
                yield chunk
        except Exception as exc:
            log_event(
                logger,
                "llm.stream_failed",
                provider=provider,
                model=model,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error_type=exc.__class__.__name__,
            )
            raise

        usage = _usage_from_response(last_chunk, model=model) if last_chunk is not None else {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
        }
        log_event(
            logger,
            "llm.stream_completed",
            provider=provider,
            model=model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=usage["cost_usd"],
            latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

    return _logged_stream()


def create_embeddings(provider: str | None = None):
    """Create embeddings for the selected provider."""
    chosen_provider, _ = normalise_llm_selection(provider, None)
    logger.info("Creating embeddings provider=%s", chosen_provider)

    if not OPENAI_API_KEY:
        logger.error("OpenAI embeddings requested but OPENAI_API_KEY is not configured")
        raise RuntimeError("OpenAI embeddings require OPENAI_API_KEY in your environment.")

    return OpenAIEmbeddings(model=EMBEDDING_MODELS["openai"])
