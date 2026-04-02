"""Helpers for displaying currency values consistently across the app."""

from config import DEFAULT_CURRENCY

_CURRENCY_PREFIXES = {
    "USD": "$",
    "EUR": "EUR ",
    "GBP": "GBP ",
    "CAD": "CAD ",
    "AUD": "AUD ",
    "JPY": "JPY ",
    "CHF": "CHF ",
    "SGD": "SGD ",
    "AED": "AED ",
    "NZD": "NZD ",
}


def normalise_currency(currency: str | None) -> str:
    """Return an uppercase currency code or the default currency."""
    return str(currency or DEFAULT_CURRENCY).upper()


def currency_prefix(currency: str | None) -> str:
    """Return the display prefix for a currency."""
    code = normalise_currency(currency)
    return _CURRENCY_PREFIXES.get(code, f"{code} ")


def format_currency(amount: float | int, currency: str | None, decimals: int = 0) -> str:
    """Format a numeric amount using the app's currency display style."""
    prefix = currency_prefix(currency)
    return f"{prefix}{float(amount):,.{decimals}f}"
