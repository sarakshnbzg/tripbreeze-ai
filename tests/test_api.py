"""Tests for presentation/api.py."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fastapi.responses import Response

from infrastructure.persistence import memory_store
from presentation import api
from presentation import auth as auth_module
from presentation.auth import create_session_token, set_session_cookie
from presentation import api_routes_auth as auth_routes
from presentation import api_routes_planning as planning_routes


client = TestClient(api.app)


def auth_headers(user_id: str = "test_user") -> dict[str, str]:
    token = create_session_token(user_id)
    csrf_token = memory_store.get_csrf_token_for_session(token)
    return {
        "Authorization": f"Bearer {token}",
        "x-csrf-token": csrf_token or "",
    }


class DummyGraph:
    def __init__(self, values=None):
        self._values = values or {}

    def get_state(self, config):
        return SimpleNamespace(values=self._values)


class TestAPIHelpers:
    def test_sse_event_serializes_dict_payload(self):
        event = api._sse_event("node_start", {"label": "Planning"})

        assert event == 'event: node_start\ndata: {"label": "Planning"}\n\n'

    def test_set_session_cookie_rejects_empty_secret(self, monkeypatch):
        monkeypatch.setattr("presentation.auth.SESSION_SECRET", "")

        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            set_session_cookie(Response(), "test_user")


class TestAPIEndpoints:
    def setup_method(self):
        auth_routes._AUTH_ATTEMPTS.clear()
        memory_store._in_memory_sessions.clear()

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

    def test_login_sets_strict_http_only_cookie(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "verify_user", lambda user_id, password: True)
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})

        response = client.post(
            "/api/auth/login",
            json={"user_id": "test_user", "password": "super-secret"},
        )

        assert response.status_code == 200
        cookie_header = response.headers["set-cookie"]
        assert "HttpOnly" in cookie_header
        assert "SameSite=strict" in cookie_header
        assert response.json()["csrf_token"]

    def test_login_rate_limits_repeated_attempts(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "verify_user", lambda user_id, password: False)

        for _ in range(auth_routes._AUTH_RATE_LIMIT_MAX_ATTEMPTS):
            response = client.post(
                "/api/auth/login",
                headers={"x-forwarded-for": "203.0.113.10"},
                json={"user_id": "test_user", "password": "wrong"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/auth/login",
            headers={"x-forwarded-for": "203.0.113.10"},
            json={"user_id": "test_user", "password": "wrong"},
        )

        assert blocked.status_code == 429
        assert "Too many authentication attempts" in blocked.json()["detail"]

    def test_login_rotates_existing_sessions_for_user(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "verify_user", lambda user_id, password: True)
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})

        stale_token = create_session_token("test_user")
        stale_headers = {"Authorization": f"Bearer {stale_token}"}
        allowed_before_login = client.get("/api/profile/test_user", headers=stale_headers)
        assert allowed_before_login.status_code == 200

        response = client.post(
            "/api/auth/login",
            json={"user_id": "test_user", "password": "super-secret"},
        )

        assert response.status_code == 200

        denied_after_login = client.get("/api/profile/test_user", headers=stale_headers)
        assert denied_after_login.status_code == 401
        assert denied_after_login.json()["detail"] == "Authentication required"

    def test_logout_invalidates_bearer_session(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})

        token = create_session_token("test_user")
        headers = {
            "Authorization": f"Bearer {token}",
            "x-csrf-token": memory_store.get_csrf_token_for_session(token) or "",
        }

        response = client.post("/api/auth/logout", headers=headers)

        assert response.status_code == 200

        denied = client.get("/api/profile/test_user", headers=headers)
        assert denied.status_code == 401
        assert denied.json()["detail"] == "Authentication required"

    def test_update_profile_rejects_missing_csrf_token(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})

        token = create_session_token("test_user")
        response = client.put(
            "/api/profile/test_user",
            headers={"Authorization": f"Bearer {token}"},
            json={"profile": {"home_city": "Berlin"}},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF validation failed"

    def test_update_profile_rejects_invalid_origin(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})

        token = create_session_token("test_user")
        response = client.put(
            "/api/profile/test_user",
            headers={
                "Authorization": f"Bearer {token}",
                "x-csrf-token": memory_store.get_csrf_token_for_session(token) or "",
                "origin": "https://evil.example",
            },
            json={"profile": {"home_city": "Berlin"}},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid request origin"

    def test_idle_session_expires_after_inactivity(self, monkeypatch):
        monkeypatch.setattr(auth_routes, "load_profile", lambda user_id: {"user_id": user_id})
        monkeypatch.setattr(auth_module, "SESSION_IDLE_TIMEOUT_SECONDS", 5)

        clock = {"now": 1_000}
        monkeypatch.setattr(memory_store.time, "time", lambda: clock["now"])

        token = create_session_token("test_user")
        headers = {"Authorization": f"Bearer {token}"}

        first = client.get("/api/profile/test_user", headers=headers)
        assert first.status_code == 200

        clock["now"] += 6

        expired = client.get("/api/profile/test_user", headers=headers)
        assert expired.status_code == 401
        assert expired.json()["detail"] == "Authentication required"

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
