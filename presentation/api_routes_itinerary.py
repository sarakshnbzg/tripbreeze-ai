"""Itinerary export and delivery routes for the FastAPI backend."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from settings import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_SENDER_EMAIL,
    SMTP_SENDER_PASSWORD,
    SMTP_USE_TLS,
)
from infrastructure.email_sender import SMTPConfig, send_itinerary_email
from infrastructure.pdf_generator import generate_trip_pdf
from presentation.api_security import (
    enforce_content_length,
    enforce_json_size,
    enforce_rate_limit,
    enforce_text_length,
    log_and_raise_api_error,
)
from presentation.api_models import ItineraryEmailRequest, ItineraryPdfRequest
from presentation.api_runtime import logger

router = APIRouter()
_MAX_ITINERARY_REQUEST_BYTES = 1_000_000
_MAX_ITINERARY_TEXT_CHARS = 200_000
_MAX_GRAPH_STATE_CHARS = 500_000


@router.post("/api/itinerary/pdf")
async def itinerary_pdf(req: ItineraryPdfRequest, request: Request):
    """Generate a PDF for a final itinerary."""
    enforce_rate_limit(
        "itinerary_pdf",
        request,
        max_attempts=20,
        window_seconds=300,
        message="Too many PDF export requests. Please wait a few minutes and try again.",
    )
    enforce_content_length(
        request,
        max_bytes=_MAX_ITINERARY_REQUEST_BYTES,
        message="PDF export request is too large.",
    )
    if not req.final_itinerary.strip():
        raise HTTPException(status_code=400, detail="Final itinerary is required")
    enforce_text_length(
        "file_name",
        req.file_name,
        max_chars=200,
        message="Export filename is too long.",
    )
    enforce_text_length(
        "final_itinerary",
        req.final_itinerary,
        max_chars=_MAX_ITINERARY_TEXT_CHARS,
        message="Final itinerary is too large to export.",
    )
    enforce_json_size(
        "graph_state",
        req.graph_state,
        max_chars=_MAX_GRAPH_STATE_CHARS,
        message="Itinerary export data is too large.",
    )

    try:
        pdf_bytes = generate_trip_pdf(
            final_itinerary=req.final_itinerary,
            graph_state=req.graph_state or {},
        )
    except Exception as exc:
        log_and_raise_api_error(
            event="api.itinerary_pdf_failed",
            public_message="PDF generation failed. Please try again later.",
            exc=exc,
            status_code=500,
            path="/api/itinerary/pdf",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{req.file_name or "trip_itinerary.pdf"}"'},
    )


@router.post("/api/itinerary/email")
async def itinerary_email(req: ItineraryEmailRequest, request: Request):
    """Email the itinerary PDF to a recipient."""
    enforce_rate_limit(
        "itinerary_email",
        request,
        max_attempts=8,
        window_seconds=300,
        message="Too many itinerary email requests. Please wait a few minutes and try again.",
    )
    enforce_content_length(
        request,
        max_bytes=_MAX_ITINERARY_REQUEST_BYTES,
        message="Itinerary email request is too large.",
    )
    if not req.recipient_email.strip():
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not req.final_itinerary.strip():
        raise HTTPException(status_code=400, detail="Final itinerary is required")
    enforce_text_length(
        "recipient_email",
        req.recipient_email,
        max_chars=320,
        message="Recipient email is too long.",
    )
    enforce_text_length(
        "final_itinerary",
        req.final_itinerary,
        max_chars=_MAX_ITINERARY_TEXT_CHARS,
        message="Final itinerary is too large to email.",
    )
    enforce_json_size(
        "graph_state",
        req.graph_state,
        max_chars=_MAX_GRAPH_STATE_CHARS,
        message="Itinerary email data is too large.",
    )
    enforce_text_length(
        "recipient_name",
        req.recipient_name,
        max_chars=200,
        message="Recipient name is too long.",
    )

    try:
        pdf_bytes = generate_trip_pdf(
            final_itinerary=req.final_itinerary,
            graph_state=req.graph_state or {},
        )
        smtp_config = SMTPConfig(
            smtp_host=SMTP_HOST,
            smtp_port=SMTP_PORT,
            sender_email=SMTP_SENDER_EMAIL,
            sender_password=SMTP_SENDER_PASSWORD,
            use_tls=SMTP_USE_TLS,
        )
        success, message = send_itinerary_email(
            recipient_email=req.recipient_email.strip(),
            pdf_bytes=pdf_bytes,
            smtp_config=smtp_config,
            recipient_name=req.recipient_name.strip() or "traveler",
        )
    except Exception as exc:
        log_and_raise_api_error(
            event="api.itinerary_email_failed",
            public_message="Itinerary email failed. Please try again later.",
            exc=exc,
            status_code=500,
            path="/api/itinerary/email",
            recipient_email=req.recipient_email.strip(),
        )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}
