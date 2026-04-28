"""Health and utility routes for the FastAPI backend."""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from presentation.api_security import enforce_content_length, enforce_rate_limit, log_and_raise_api_error
from presentation.api_runtime import logger

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


@router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Lightweight container/lb health endpoint."""
    return {"status": "ok"}


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
        return {"text": transcript.text}
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
