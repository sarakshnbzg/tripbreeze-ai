"""Tests for presentation/api.py."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from presentation import api


client = TestClient(api.app)


class DummyGraph:
    def __init__(self, values=None):
        self._values = values or {}

    def get_state(self, config):
        return SimpleNamespace(values=self._values)


class TestAPIHelpers:
    def test_sse_event_serializes_dict_payload(self):
        event = api._sse_event("node_start", {"label": "Planning"})

        assert event == 'event: node_start\ndata: {"label": "Planning"}\n\n'


class TestAPIEndpoints:
    def test_search_rejects_unavailable_provider(self, monkeypatch):
        monkeypatch.setattr(api, "get_provider_status", lambda provider: (False, "Provider unavailable"))

        response = client.post("/api/search", json={"llm_provider": "openai"})

        assert response.status_code == 400
        assert response.json()["detail"] == "Provider unavailable"

    def test_get_state_returns_404_for_missing_thread(self, monkeypatch):
        monkeypatch.setattr(api, "_get_graph", lambda: DummyGraph(values={}))

        response = client.get("/api/search/thread-123/state")

        assert response.status_code == 404

    def test_get_state_returns_values_with_thread_id(self, monkeypatch):
        monkeypatch.setattr(api, "_get_graph", lambda: DummyGraph(values={"current_step": "review"}))

        response = client.get("/api/search/thread-123/state")

        assert response.status_code == 200
        assert response.json()["current_step"] == "review"
        assert response.json()["thread_id"] == "thread-123"

    def test_return_flights_passes_through_time_window(self, monkeypatch):
        captured = {}

        def fake_fetch_return_flights(**kwargs):
            captured.update(kwargs)
            return [{"airline": "Test Air"}]

        monkeypatch.setattr(api, "fetch_return_flights", fake_fetch_return_flights)

        response = client.post(
            "/api/search/thread-123/return-flights",
            json={
                "origin": "Berlin",
                "destination": "Paris",
                "departure_date": "2026-06-01",
                "return_date": "2026-06-08",
                "departure_token": "tok_123",
                "return_time_window": [9, 17],
            },
        )

        assert response.status_code == 200
        assert response.json() == [{"airline": "Test Air"}]
        assert captured["return_time_window"] == (9, 17)

    def test_clarify_rejects_blank_answer(self):
        response = client.post("/api/search/thread-123/clarify", json={"answer": "   "})

        assert response.status_code == 400
        assert response.json()["detail"] == "Answer cannot be empty"

    def test_approve_rejects_unavailable_provider(self, monkeypatch):
        monkeypatch.setattr(api, "get_provider_status", lambda provider: (False, "Provider unavailable"))

        response = client.post(
            "/api/search/thread-123/approve",
            json={"llm_provider": "openai"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Provider unavailable"
