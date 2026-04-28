"""Tests for presentation/api.py."""

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from presentation import api
from presentation.auth import create_session_token
from presentation import api_routes_auth as auth_routes
from presentation import api_routes_planning as planning_routes


client = TestClient(api.app)


def auth_headers(user_id: str = "test_user") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_session_token(user_id)}"}


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
    def test_search_requires_authentication(self):
        response = client.post("/api/search", json={"user_id": "test_user", "llm_provider": "openai"})

        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"

    def test_search_rejects_unavailable_provider(self, monkeypatch):
        monkeypatch.setattr(planning_routes, "get_provider_status", lambda provider: (False, "Provider unavailable"))

        response = client.post(
            "/api/search",
            headers=auth_headers(),
            json={"user_id": "spoofed_user", "llm_provider": "openai"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Provider unavailable"

    def test_get_profile_rejects_other_users(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})

        response = client.get("/api/profile/alice", headers=auth_headers("bob"))

        assert response.status_code == 403
        assert response.json()["detail"] == "You may only access your own profile"

    def test_get_state_returns_404_for_missing_thread(self, monkeypatch):
        monkeypatch.setattr(planning_routes, "get_graph", lambda: DummyGraph(values={}))

        response = client.get("/api/search/thread-123/state", headers=auth_headers())

        assert response.status_code == 404

    def test_get_state_returns_values_with_thread_id(self, monkeypatch):
        monkeypatch.setattr(
            planning_routes,
            "get_graph",
            lambda: DummyGraph(values={"current_step": "review", "user_id": "test_user"}),
        )

        response = client.get("/api/search/thread-123/state", headers=auth_headers())

        assert response.status_code == 200
        assert response.json()["current_step"] == "review"
        assert response.json()["thread_id"] == "thread-123"

    def test_get_state_rejects_other_users_threads(self, monkeypatch):
        monkeypatch.setattr(
            planning_routes,
            "get_graph",
            lambda: DummyGraph(values={"current_step": "review", "user_id": "alice"}),
        )

        response = client.get("/api/search/thread-123/state", headers=auth_headers("bob"))

        assert response.status_code == 403
        assert response.json()["detail"] == "You may only access your own planning session"

    def test_return_flights_passes_through_time_window(self, monkeypatch):
        captured = {}

        def fake_fetch_return_flights(**kwargs):
            captured.update(kwargs)
            return [{"airline": "Test Air"}]

        monkeypatch.setattr(planning_routes, "fetch_return_flights", fake_fetch_return_flights)
        monkeypatch.setattr(
            planning_routes,
            "get_graph",
            lambda: DummyGraph(values={"current_step": "review", "user_id": "test_user"}),
        )

        response = client.post(
            "/api/search/thread-123/return-flights",
            headers=auth_headers(),
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
        response = client.post("/api/search/thread-123/clarify", headers=auth_headers(), json={"answer": "   "})

        assert response.status_code == 400
        assert response.json()["detail"] == "Answer cannot be empty"

    def test_approve_rejects_unavailable_provider(self, monkeypatch):
        monkeypatch.setattr(planning_routes, "get_provider_status", lambda provider: (False, "Provider unavailable"))
        monkeypatch.setattr(
            planning_routes,
            "get_graph",
            lambda: DummyGraph(values={"current_step": "review", "user_id": "test_user"}),
        )

        response = client.post(
            "/api/search/thread-123/approve",
            headers=auth_headers(),
            json={"llm_provider": "openai"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Provider unavailable"

    def test_approve_routes_revision_feedback_to_revision_runner(self, monkeypatch):
        class DummyLoop:
            def __init__(self):
                self.calls = []

            def run_in_executor(self, executor, fn, *args):
                self.calls.append(fn)

        loop = DummyLoop()
        monkeypatch.setattr(planning_routes, "get_provider_status", lambda provider: (True, ""))
        monkeypatch.setattr(planning_routes.asyncio, "get_running_loop", lambda: loop)
        monkeypatch.setattr(
            planning_routes,
            "get_graph",
            lambda: DummyGraph(values={"current_step": "review", "user_id": "test_user"}),
        )

        response = asyncio.run(
            planning_routes.approve(
                "thread-123",
                api.ApproveRequest(
                    llm_provider="openai",
                    feedback_type="revise_plan",
                    user_feedback="Show cheaper hotels.",
                ),
                SimpleNamespace(state=SimpleNamespace(authenticated_user="test_user")),
            )
        )

        assert response.status_code == 200
        assert loop.calls == [planning_routes.run_post_review_sync]
