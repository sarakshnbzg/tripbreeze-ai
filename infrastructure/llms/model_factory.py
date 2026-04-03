"""Factory helpers for creating chat and embedding models from user-selected providers."""

from __future__ import annotations

import importlib.util
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings

from config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    EMBEDDING_MODELS,
    GOOGLE_API_KEY,
    MODEL_COSTS,
    OPENAI_API_KEY,
)
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

OPENAI_MODELS = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-3.5-turbo"]
GOOGLE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


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
                "Run `pip install -r requirements.txt`.",
            )
        if not GOOGLE_API_KEY:
            return (
                False,
                "Google Gemini support requires `GOOGLE_API_KEY` or `GEMINI_API_KEY` in `.env`.",
            )
        return True, ""

    if not OPENAI_API_KEY:
        return False, "OpenAI support requires `OPENAI_API_KEY` in `.env`."

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
