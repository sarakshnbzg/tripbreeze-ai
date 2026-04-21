"""Itinerary export and delivery routes for the FastAPI backend."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_SENDER_EMAIL,
    SMTP_SENDER_PASSWORD,
    SMTP_USE_TLS,
)
from infrastructure.email_sender import SMTPConfig, send_itinerary_email
from infrastructure.pdf_generator import generate_trip_pdf
from presentation.api_models import ItineraryEmailRequest, ItineraryPdfRequest
from presentation.api_runtime import logger

router = APIRouter()


@router.post("/api/itinerary/pdf")
async def itinerary_pdf(req: ItineraryPdfRequest):
    """Generate a PDF for a final itinerary."""
    if not req.final_itinerary.strip():
        raise HTTPException(status_code=400, detail="Final itinerary is required")

    try:
        pdf_bytes = generate_trip_pdf(
            final_itinerary=req.final_itinerary,
            graph_state=req.graph_state or {},
        )
    except Exception as exc:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{req.file_name or "trip_itinerary.pdf"}"'},
    )


@router.post("/api/itinerary/email")
async def itinerary_email(req: ItineraryEmailRequest):
    """Email the itinerary PDF to a recipient."""
    if not req.recipient_email.strip():
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not req.final_itinerary.strip():
        raise HTTPException(status_code=400, detail="Final itinerary is required")

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
        logger.exception("Itinerary email failed")
        raise HTTPException(status_code=500, detail=f"Itinerary email failed: {exc}") from exc

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}
