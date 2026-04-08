"""Tests for presentation/streamlit_app.py helper functions."""

from datetime import date

from presentation.streamlit_app import _build_structured_fields_from_form, _summarise_token_usage


class TestSummariseTokenUsage:
    def test_groups_usage_by_model_and_phase(self):
        usage = [
            {
                "node": "trip_intake",
                "model": "gpt-4o-mini",
                "input_tokens": 100,
                "output_tokens": 20,
                "cost": 0.001,
            },
            {
                "node": "destination_research",
                "model": "gpt-4o-mini",
                "input_tokens": 50,
                "output_tokens": 10,
                "cost": 0.0005,
            },
            {
                "node": "trip_finaliser",
                "model": "gemini-2.5-flash",
                "input_tokens": 200,
                "output_tokens": 40,
                "cost": 0.002,
            },
        ]

        summary = _summarise_token_usage(usage)

        assert summary["input_tokens"] == 350
        assert summary["output_tokens"] == 70
        assert summary["cost"] == 0.0035
        assert summary["by_phase"]["Planning"]["input_tokens"] == 150
        assert summary["by_phase"]["Final Itinerary"]["input_tokens"] == 200
        assert summary["by_model"]["gpt-4o-mini"]["calls"] == 2
        assert summary["by_model"]["gemini-2.5-flash"]["calls"] == 1


class TestBuildStructuredFieldsFromForm:
    def test_ignores_untouched_defaults_when_free_text_is_present(self):
        result = _build_structured_fields_from_form(
            free_text="I want to fly from Berlin to London on the 20th of April for 2 days. Plan my trip.",
            origin="Berlin",
            destination="",
            departure_date=date(2026, 4, 22),
            return_date=date(2026, 4, 29),
            one_way=False,
            num_nights=None,
            num_travelers=1,
            budget_limit=0,
            currency="EUR",
            preferences="",
            default_origin="Berlin",
            default_departure_date=date(2026, 4, 22),
            default_return_date=date(2026, 4, 29),
            default_currency="EUR",
        )

        assert result == {}

    def test_keeps_explicit_refinements_with_free_text(self):
        result = _build_structured_fields_from_form(
            free_text="Plan my trip to London.",
            origin="Berlin",
            destination="London",
            departure_date=date(2026, 4, 24),
            return_date=date(2026, 4, 27),
            one_way=False,
            num_nights=None,
            num_travelers=2,
            budget_limit=1200,
            currency="USD",
            preferences="direct flights only",
            default_origin="Berlin",
            default_departure_date=date(2026, 4, 22),
            default_return_date=date(2026, 4, 29),
            default_currency="EUR",
        )

        assert result["destination"] == "London"
        assert result["departure_date"] == "2026-04-24"
        assert result["return_date"] == "2026-04-27"
        assert result["num_travelers"] == 2
        assert result["budget_limit"] == 1200
        assert result["currency"] == "USD"
