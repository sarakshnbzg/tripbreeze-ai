"""Tests for infrastructure/pdf_generator.py."""

from infrastructure.pdf_generator import _normalize_pdf_text


def test_normalize_pdf_text_replaces_problematic_symbols():
    text = 'Trip Itinerary • Vienna → Budapest — "Highlights" · Food ⭐'

    normalized = _normalize_pdf_text(text)

    assert normalized == 'Trip Itinerary - Vienna -> Budapest - "Highlights" - Food *'


def test_normalize_pdf_text_preserves_plain_ascii():
    text = "Day 2 - Museum Quarter"

    assert _normalize_pdf_text(text) == text
