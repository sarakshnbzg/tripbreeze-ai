"""Integration-style tests for the planner SSE API flow."""

import queue

from fastapi.testclient import TestClient

from presentation import api
from presentation import api_routes_planning as planning_routes
from presentation.api_sse import SENTINEL, sse_event

client = TestClient(api.app)


class ImmediateLoop:
    def __init__(self):
        self.calls = []

    def run_in_executor(self, executor, fn, *args):
        self.calls.append((fn, args))
        result = fn(*args)

        class ImmediateResult:
            def __await__(self_inner):
                async def _resolve():
                    return result

                return _resolve().__await__()

        return ImmediateResult()


def test_search_stream_returns_clarification_event(monkeypatch):
    def fake_run_planning_sync(q: queue.Queue, initial_state: dict, config: dict) -> None:
        q.put(sse_event("node_start", {"node": "trip_intake", "label": "Understanding your trip request..."}))
        q.put(sse_event("clarification", {
            "thread_id": config["configurable"]["thread_id"],
            "question": "Which dates work best?",
            "missing_fields": ["departure_date"],
        }))
        q.put(SENTINEL)

    loop = ImmediateLoop()
    monkeypatch.setattr(planning_routes, "get_provider_status", lambda provider: (True, ""))
    monkeypatch.setattr(planning_routes, "run_planning_sync", fake_run_planning_sync)
    monkeypatch.setattr(planning_routes.asyncio, "get_event_loop", lambda: loop)

    response = client.post("/api/search", json={
        "user_id": "sara",
        "free_text_query": "Plan a trip to Paris",
        "llm_provider": "openai",
    })

    assert response.status_code == 200
    assert "event: node_start" in response.text
    assert "event: clarification" in response.text
    assert "Which dates work best?" in response.text
    assert "event: done" in response.text


def test_clarify_stream_returns_state_event(monkeypatch):
    def fake_run_clarification_sync(q: queue.Queue, thread_id: str, answer: str) -> None:
        assert thread_id == "thread-123"
        assert answer == "June 10"
        q.put(sse_event("state", {
            "thread_id": thread_id,
            "trip_request": {"destination": "Paris", "departure_date": "2026-06-10"},
        }))
        q.put(SENTINEL)

    loop = ImmediateLoop()
    monkeypatch.setattr(planning_routes, "run_clarification_sync", fake_run_clarification_sync)
    monkeypatch.setattr(planning_routes.asyncio, "get_event_loop", lambda: loop)

    response = client.post("/api/search/thread-123/clarify", json={"answer": "June 10"})

    assert response.status_code == 200
    assert "event: state" in response.text
    assert '"destination": "Paris"' in response.text
    assert "event: done" in response.text


def test_approve_stream_returns_tokens_and_final_state(monkeypatch):
    def fake_run_post_review_sync(q: queue.Queue, thread_id: str, state_updates: dict) -> None:
        assert thread_id == "thread-123"
        assert state_updates["selected_flight"]["airline"] == "Test Air"
        q.put(sse_event("node_start", {"node": "finalise", "label": "Finalising your itinerary..."}))
        q.put(sse_event("token", {"content": "Day 1"}))
        q.put(sse_event("token", {"content": ": Arrive"}))
        q.put(sse_event("state", {
            "thread_id": thread_id,
            "final_itinerary": "Day 1: Arrive",
        }))
        q.put(SENTINEL)

    loop = ImmediateLoop()
    monkeypatch.setattr(planning_routes, "get_provider_status", lambda provider: (True, ""))
    monkeypatch.setattr(planning_routes, "run_post_review_sync", fake_run_post_review_sync)
    monkeypatch.setattr(planning_routes.asyncio, "get_event_loop", lambda: loop)

    response = client.post("/api/search/thread-123/approve", json={
        "llm_provider": "openai",
        "feedback_type": "rewrite_itinerary",
        "user_feedback": "Keep it relaxed.",
        "selected_flight": {"airline": "Test Air"},
        "selected_hotel": {"name": "Hotel Example"},
    })

    assert response.status_code == 200
    assert "event: node_start" in response.text
    assert "event: token" in response.text
    assert "Day 1" in response.text
    assert '"final_itinerary": "Day 1: Arrive"' in response.text
    assert "event: done" in response.text
