"""Integration-style tests for the planner SSE API flow."""

import asyncio
import queue
from types import SimpleNamespace

from presentation import api
from presentation import api_routes_planning as planning_routes
from presentation import api_sse
from presentation.api_sse import SENTINEL, sse_event


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


def make_request(user_id: str = "sara"):
    return SimpleNamespace(state=SimpleNamespace(authenticated_user=user_id))


def make_graph(user_id: str = "sara"):
    return type("Graph", (), {"get_state": lambda self, config: type("State", (), {"values": {"user_id": user_id}})()})()


async def collect_streaming_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)


def test_search_stream_returns_clarification_event(monkeypatch):
    def fake_run_planning_sync(q: queue.Queue, initial_state: dict, config: dict) -> None:
        assert initial_state["user_id"] == "sara"
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
    monkeypatch.setattr(planning_routes.asyncio, "get_running_loop", lambda: loop)

    response = asyncio.run(
        planning_routes.search(
            api.SearchRequest(
                user_id="spoofed-user",
                free_text_query="Plan a trip to Paris",
                llm_provider="openai",
            ),
            make_request(),
        )
    )
    body = asyncio.run(collect_streaming_body(response))

    assert response.status_code == 200
    assert "event: node_start" in body
    assert "event: clarification" in body
    assert "Which dates work best?" in body
    assert "event: done" in body


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
    monkeypatch.setattr(planning_routes.asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(planning_routes, "get_graph", lambda: make_graph())

    response = asyncio.run(
        planning_routes.clarify(
            "thread-123",
            api.ClarifyRequest(answer="June 10"),
            make_request(),
        )
    )
    body = asyncio.run(collect_streaming_body(response))

    assert response.status_code == 200
    assert "event: state" in body
    assert '"destination": "Paris"' in body
    assert "event: done" in body


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
    monkeypatch.setattr(planning_routes.asyncio, "get_running_loop", lambda: loop)
    monkeypatch.setattr(planning_routes, "get_graph", lambda: make_graph())

    response = asyncio.run(
        planning_routes.approve(
            "thread-123",
            api.ApproveRequest(
                llm_provider="openai",
                feedback_type="rewrite_itinerary",
                user_feedback="Keep it relaxed.",
                selected_flight={"airline": "Test Air"},
                selected_hotel={"name": "Hotel Example"},
            ),
            make_request(),
        )
    )
    body = asyncio.run(collect_streaming_body(response))

    assert response.status_code == 200
    assert "event: node_start" in body
    assert "event: token" in body
    assert "Day 1" in body
    assert '"final_itinerary": "Day 1: Arrive"' in body
    assert "event: done" in body


def test_run_planning_sync_logs_step_and_run_summary(monkeypatch):
    class FakeGraph:
        def stream(self, initial_state, config):
            yield {
                "trip_intake": {
                    "messages": [{"role": "assistant", "content": "Parsed trip"}],
                    "token_usage": [
                        {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "cost_usd": 0.001,
                        }
                    ],
                    "current_step": "intake_complete",
                }
            }

        def get_state(self, config):
            return SimpleNamespace(values={"user_id": "sara", "token_usage": [{"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001}], "current_step": "intake_complete"})

    events = []
    monkeypatch.setattr(api_sse, "get_graph", lambda: FakeGraph())
    monkeypatch.setattr(api_sse, "log_event", lambda logger, event, **fields: events.append((event, fields)))

    q: queue.Queue = queue.Queue()
    api_sse.run_planning_sync(q, {"user_id": "sara"}, {"configurable": {"thread_id": "thread-123"}})

    assert any(event == "workflow.step_completed" and fields["step"] == "trip_intake" for event, fields in events)
    assert any(event == "workflow.run_completed" and fields["thread_id"] == "thread-123" for event, fields in events)
