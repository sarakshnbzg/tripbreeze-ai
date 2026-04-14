"""Send emails with PDF attachments via generic SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


class SMTPConfig:
    """Configuration for SMTP email sending."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender_email: str,
        sender_password: str,
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.use_tls = use_tls

    def is_configured(self) -> bool:
        """Check if all required SMTP settings are provided."""
        return bool(
            self.smtp_host
            and self.smtp_port
            and self.sender_email
            and self.sender_password
        )


def send_itinerary_email(
    recipient_email: str,
    pdf_bytes: bytes,
    smtp_config: SMTPConfig,
    recipient_name: Optional[str] = None,
) -> tuple[bool, str]:
    """Send trip itinerary PDF via email.

    Args:
        recipient_email: Email address of the recipient
        pdf_bytes: PDF content as bytes
        smtp_config: SMTP configuration object
        recipient_name: Optional name of the recipient for personalization

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not smtp_config.is_configured():
        return (
            False,
            "SMTP not configured. Please set SMTP_HOST, SMTP_PORT, SENDER_EMAIL, and SENDER_PASSWORD.",
        )

    if not recipient_email or "@" not in recipient_email:
        return False, "Invalid recipient email address."

    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = smtp_config.sender_email
        msg["To"] = recipient_email
        msg["Subject"] = "Your TripBreeze AI Itinerary"

        # Email body
        body = f"""Hello{f' {recipient_name}' if recipient_name else ''},

Your TripBreeze AI trip itinerary is attached as a PDF.

Please review the details and enjoy your trip!

Best regards,
TripBreeze AI Team"""

        msg.attach(MIMEText(body, "plain"))

        # Attach PDF
        pdf_attachment = MIMEBase("application", "octet-stream")
        pdf_attachment.set_payload(pdf_bytes)
        encoders.encode_base64(pdf_attachment)
        pdf_attachment.add_header("Content-Disposition", "attachment", filename="trip_itinerary.pdf")
        msg.attach(pdf_attachment)

        # Send email
        logger.info(
            "Connecting to SMTP server %s:%d for sending to %s",
            smtp_config.smtp_host,
            smtp_config.smtp_port,
            recipient_email,
        )

        with smtplib.SMTP(smtp_config.smtp_host, smtp_config.smtp_port) as server:
            if smtp_config.use_tls:
                server.starttls()
            server.login(smtp_config.sender_email, smtp_config.sender_password)
            server.send_message(msg)

        logger.info("Email sent successfully to %s", recipient_email)
        return True, f"Itinerary sent to {recipient_email}!"

    except smtplib.SMTPAuthenticationError:
        error_msg = "SMTP authentication failed. Check your sender email and password."
        logger.error(error_msg)
        return False, error_msg
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.exception(error_msg)
        return False, error_msg
