"""Generate and serve a single LLM-designed cover image for the final itinerary."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from infrastructure.apis.moderation_client import ModerationBlockedError, ModerationUnavailableError, check_text_allowed
from infrastructure.llms.model_factory import create_chat_model, extract_token_usage, invoke_with_retry
from infrastructure.logging_utils import get_logger, log_event
from settings import (
    ITINERARY_COVER_IMAGE_ENABLED,
    ITINERARY_COVER_IMAGE_MODEL,
    ITINERARY_COVER_IMAGE_SIZE,
    ITINERARY_COVER_IMAGE_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
    PROJECT_ROOT,
)

logger = get_logger(__name__)
GENERATED_IMAGE_DIR = PROJECT_ROOT / ".generated" / "itinerary_covers"


class ItineraryCoverConcept(BaseModel):
    """Compact metadata for a single itinerary cover image."""

    title: str = Field(description="Short title for the image card.")
    alt_text: str = Field(description="Accessible alt text for the rendered image.")
    prompt: str = Field(description="Final image-generation prompt.")
    caption: str = Field(description="One-sentence caption tying the image to the trip.")


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    return text[start : end + 1]


def _build_cover_prompt_request(*, trip_request: dict[str, Any], itinerary_data: dict[str, Any], mode: str) -> str:
    return f"""Create the creative direction for ONE travel itinerary cover image.

Return valid JSON with exactly these keys:
- title
- alt_text
- prompt
- caption

Rules:
- The prompt should describe a single cinematic cover image for the trip.
- Make it feel like a premium travel editorial or poster, not generic AI art.
- Do not include text overlays, watermarks, logos, signage text, or split panels.
- Reflect destination, mood, season, weather, and trip pace when supported by the itinerary.
- For multi-city trips, blend the route into one coherent scene instead of a collage.
- Keep alt_text concrete and accessible.
- Keep caption under 20 words.

Trip mode: {mode}
Trip request JSON:
{json.dumps(trip_request, indent=2)}

Structured itinerary JSON:
{json.dumps(itinerary_data, indent=2)}
"""


def _generate_cover_concept(
    *,
    trip_request: dict[str, Any],
    itinerary_data: dict[str, Any],
    llm_provider: str,
    llm_model: str,
) -> tuple[ItineraryCoverConcept, dict[str, Any]]:
    llm = create_chat_model(llm_provider, llm_model, temperature=0.4)
    response = invoke_with_retry(
        llm,
        _build_cover_prompt_request(
            trip_request=trip_request,
            itinerary_data=itinerary_data,
            mode="multi_city" if itinerary_data.get("legs") else "single_city",
        ),
    )
    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "\n".join(str(part) for part in content)
    payload = json.loads(_extract_json_object(str(content)))
    concept = ItineraryCoverConcept.model_validate(payload)
    usage = extract_token_usage(response, model=llm_model, node="itinerary_cover_prompt")
    return concept, usage


def _save_image_bytes(image_bytes: bytes) -> Path:
    GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = GENERATED_IMAGE_DIR / f"{uuid4().hex}.png"
    image_path.write_bytes(image_bytes)
    return image_path


def generate_itinerary_cover(
    *,
    trip_request: dict[str, Any],
    itinerary_data: dict[str, Any],
    llm_provider: str,
    llm_model: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return image metadata plus optional prompt-token usage.

    The image generation itself is intentionally fail-soft so itinerary delivery
    still succeeds if OpenAI image generation is unavailable.
    """
    if not ITINERARY_COVER_IMAGE_ENABLED or not OPENAI_API_KEY or not itinerary_data:
        return {}, None

    try:
        concept, usage = _generate_cover_concept(
            trip_request=trip_request,
            itinerary_data=itinerary_data,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        log_event(
            logger,
            "itinerary_cover.prompt_failed",
            error_type=type(exc).__name__,
            model=llm_model,
        )
        logger.warning("Itinerary cover prompt generation failed: %s", exc)
        return {}, None
    except Exception as exc:
        log_event(
            logger,
            "itinerary_cover.prompt_failed",
            error_type=type(exc).__name__,
            model=llm_model,
        )
        logger.warning("Itinerary cover prompt generation failed: %s", exc)
        return {}, None

    try:
        import openai

        try:
            check_text_allowed(concept.prompt, context="itinerary_cover_prompt")
        except ModerationBlockedError as exc:
            log_event(
                logger,
                "itinerary_cover.prompt_blocked",
                categories=exc.categories,
                model=ITINERARY_COVER_IMAGE_MODEL,
            )
            return {}, usage
        except ModerationUnavailableError as exc:
            log_event(
                logger,
                "itinerary_cover.moderation_unavailable",
                error_type=type(exc).__name__,
                model=ITINERARY_COVER_IMAGE_MODEL,
            )
            return {}, usage

        client = openai.OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=ITINERARY_COVER_IMAGE_TIMEOUT_SECONDS,
        )
        result = client.images.generate(
            model=ITINERARY_COVER_IMAGE_MODEL,
            prompt=concept.prompt,
            size=ITINERARY_COVER_IMAGE_SIZE,
        )
        first_image = result.data[0] if getattr(result, "data", None) else None
        if first_image is None:
            return {}, usage

        if getattr(first_image, "b64_json", None):
            image_path = _save_image_bytes(base64.b64decode(first_image.b64_json))
            image_url = f"/api/generated-images/{image_path.name}"
        else:
            image_url = str(getattr(first_image, "url", "") or "").strip()
            if not image_url:
                return {}, usage

        log_event(
            logger,
            "itinerary_cover.generated",
            model=ITINERARY_COVER_IMAGE_MODEL,
            size=ITINERARY_COVER_IMAGE_SIZE,
        )
        return {
            "image_url": image_url,
            "title": concept.title,
            "alt_text": concept.alt_text,
            "caption": concept.caption,
            "prompt": concept.prompt,
            "model": ITINERARY_COVER_IMAGE_MODEL,
        }, usage
    except Exception as exc:
        log_event(
            logger,
            "itinerary_cover.image_failed",
            error_type=type(exc).__name__,
            model=ITINERARY_COVER_IMAGE_MODEL,
        )
        logger.warning("Itinerary cover image generation failed: %s", exc)
        return {}, usage
