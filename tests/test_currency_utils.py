"""Tests for infrastructure/currency_utils.py."""

from infrastructure.currency_utils import currency_prefix, format_currency, normalise_currency


class TestNormaliseCurrency:
    def test_defaults_when_missing(self):
        assert normalise_currency(None) == "EUR"

    def test_uppercases_currency(self):
        assert normalise_currency("usd") == "USD"


class TestCurrencyPrefix:
    def test_known_currency_prefix(self):
        assert currency_prefix("USD") == "$"

    def test_unknown_currency_prefix(self):
        assert currency_prefix("sek") == "SEK "


class TestFormatCurrency:
    def test_formats_usd_with_symbol(self):
        assert format_currency(1200, "USD") == "$1,200"

    def test_formats_eur_with_code_prefix(self):
        assert format_currency(1200, "EUR") == "EUR 1,200"
