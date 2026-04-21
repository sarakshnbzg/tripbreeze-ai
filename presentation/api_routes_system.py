"""Health and utility routes for the FastAPI backend."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from presentation.api_runtime import logger

router = APIRouter()


@router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Lightweight container/lb health endpoint."""
    return {"status": "ok"}


@router.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Transcribe audio to text using OpenAI Whisper."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        import openai

        client = openai.OpenAI()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename or "audio.wav", audio_bytes),
        )
        return {"text": transcript.text}
    except Exception as exc:
        logger.exception("Whisper transcription failed")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")
