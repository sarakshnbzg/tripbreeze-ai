"""Tests for presentation/streamlit_app.py helper functions."""

from presentation.streamlit_app import _summarise_token_usage


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
