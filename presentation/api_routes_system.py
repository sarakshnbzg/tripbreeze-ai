"""Health and utility routes for the FastAPI backend."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from infrastructure.apis.moderation_client import ModerationBlockedError, ModerationUnavailableError, assert_text_allowed
from presentation.api_security import enforce_content_length, enforce_rate_limit, log_and_raise_api_error
from presentation.api_runtime import logger
from infrastructure.apis.itinerary_cover_image_client import GENERATED_IMAGE_DIR

router = APIRouter()
_MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "video/webm",
}
_MODERATION_BLOCKED_MESSAGE = "This request cannot be processed because it was flagged by the safety system."
_MODERATION_UNAVAILABLE_MESSAGE = "Safety check is temporarily unavailable. Please try again later."


@router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Lightweight container/lb health endpoint."""
    return {"status": "ok"}


@router.get("/api/generated-images/{image_name:path}")
async def get_generated_image(image_name: str):
    """Serve locally cached itinerary cover images."""
    image_path = (GENERATED_IMAGE_DIR / image_name).resolve()
    try:
        image_path.relative_to(GENERATED_IMAGE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    media_type = "image/png"
    if image_path.suffix.lower() == ".jpg" or image_path.suffix.lower() == ".jpeg":
        media_type = "image/jpeg"
    return FileResponse(
        Path(image_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@router.post("/api/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...)):
    """Transcribe audio to text using OpenAI Whisper."""
    enforce_rate_limit(
        "transcribe",
        request,
        max_attempts=12,
        window_seconds=300,
        message="Too many transcription requests. Please wait a few minutes and try again.",
    )
    enforce_content_length(
        request,
        max_bytes=_MAX_AUDIO_UPLOAD_BYTES,
        message="Audio upload is too large.",
    )
    if file.content_type and file.content_type not in _ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(audio_bytes) > _MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio upload is too large.")

    try:
        import openai

        client = openai.OpenAI()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename or "audio.wav", audio_bytes),
        )
        text = str(transcript.text or "")
        try:
            assert_text_allowed(text, context="audio_transcript")
        except ModerationBlockedError as moderation_exc:
            raise HTTPException(status_code=400, detail=_MODERATION_BLOCKED_MESSAGE) from moderation_exc
        except ModerationUnavailableError as moderation_exc:
            raise HTTPException(status_code=503, detail=_MODERATION_UNAVAILABLE_MESSAGE) from moderation_exc
        return {"text": text}
    except HTTPException:
        raise
    except Exception as exc:
        log_and_raise_api_error(
            event="api.transcription_failed",
            public_message="Transcription failed. Please try again later.",
            exc=exc,
            status_code=502,
            path="/api/transcribe",
            upload_name=file.filename or "",
            content_type=file.content_type or "",
        )
