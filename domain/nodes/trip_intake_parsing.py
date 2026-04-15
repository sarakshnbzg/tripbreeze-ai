"""Date validation utilities for trip intake.

LLM-based extraction handles date parsing and duration calculation.
This module provides lightweight validation only.
"""

import re
from datetime import date


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_valid_iso_date(value: str) -> bool:
    """Return True if value is empty or a valid YYYY-MM-DD date string."""
    if not value:
        return True
    if not _ISO_DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
