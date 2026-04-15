"""Tests for infrastructure/email_sender.py."""

import smtplib

from infrastructure.email_sender import SMTPConfig, send_itinerary_email


class FakeSMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent_message = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, email, password):
        self.logged_in = (email, password)

    def send_message(self, msg):
        self.sent_message = msg


class TestSMTPConfig:
    def test_is_configured_requires_all_fields(self):
        assert SMTPConfig("", 587, "a@example.com", "pw").is_configured() is False
        assert SMTPConfig("smtp.example.com", 587, "a@example.com", "pw").is_configured() is True


class TestSendItineraryEmail:
    def test_returns_error_when_smtp_not_configured(self):
        ok, message = send_itinerary_email(
            "traveler@example.com",
            b"pdf",
            SMTPConfig("", 587, "", ""),
        )

        assert ok is False
        assert "SMTP not configured" in message

    def test_rejects_invalid_recipient_email(self):
        ok, message = send_itinerary_email(
            "not-an-email",
            b"pdf",
            SMTPConfig("smtp.example.com", 587, "sender@example.com", "pw"),
        )

        assert ok is False
        assert "Invalid recipient email" in message

    def test_sends_email_with_tls(self, monkeypatch):
        smtp = FakeSMTP("smtp.example.com", 587)
        monkeypatch.setattr(smtplib, "SMTP", lambda host, port: smtp)

        ok, message = send_itinerary_email(
            "traveler@example.com",
            b"pdf-bytes",
            SMTPConfig("smtp.example.com", 587, "sender@example.com", "pw", use_tls=True),
            recipient_name="Sara",
        )

        assert ok is True
        assert "traveler@example.com" in message
        assert smtp.started_tls is True
        assert smtp.logged_in == ("sender@example.com", "pw")
        assert smtp.sent_message["To"] == "traveler@example.com"
        assert smtp.sent_message["Subject"] == "Your TripBreeze AI Itinerary"

    def test_sends_email_without_tls_when_disabled(self, monkeypatch):
        smtp = FakeSMTP("smtp.example.com", 25)
        monkeypatch.setattr(smtplib, "SMTP", lambda host, port: smtp)

        ok, _ = send_itinerary_email(
            "traveler@example.com",
            b"pdf-bytes",
            SMTPConfig("smtp.example.com", 25, "sender@example.com", "pw", use_tls=False),
        )

        assert ok is True
        assert smtp.started_tls is False

    def test_returns_authentication_error(self, monkeypatch):
        class AuthFailSMTP(FakeSMTP):
            def login(self, email, password):
                raise smtplib.SMTPAuthenticationError(535, b"bad auth")

        monkeypatch.setattr(smtplib, "SMTP", lambda host, port: AuthFailSMTP(host, port))

        ok, message = send_itinerary_email(
            "traveler@example.com",
            b"pdf",
            SMTPConfig("smtp.example.com", 587, "sender@example.com", "pw"),
        )

        assert ok is False
        assert "authentication failed" in message.lower()

    def test_returns_generic_smtp_error(self, monkeypatch):
        class BrokenSMTP(FakeSMTP):
            def send_message(self, msg):
                raise smtplib.SMTPException("mailbox unavailable")

        monkeypatch.setattr(smtplib, "SMTP", lambda host, port: BrokenSMTP(host, port))

        ok, message = send_itinerary_email(
            "traveler@example.com",
            b"pdf",
            SMTPConfig("smtp.example.com", 587, "sender@example.com", "pw"),
        )

        assert ok is False
        assert "SMTP error" in message
