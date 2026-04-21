"""SSE helpers and sync-to-async graph bridges for the FastAPI backend."""

import asyncio
import json
import queue
from typing import Any

from langgraph.types import Command

from infrastructure.streaming import token_emitter_context
from presentation.api_runtime import NODE_LABELS, get_graph, logger

SENTINEL = object()


def sse_event(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _emit_clarification_if_present(q: queue.Queue, thread_id: str, state_snapshot: Any) -> bool:
    for task in (state_snapshot.tasks or []):
        for intr in (task.interrupts or []):
            intr_value = intr.value if hasattr(intr, "value") else intr
            if isinstance(intr_value, dict) and intr_value.get("type") == "clarification":
                q.put(sse_event("clarification", {
                    "thread_id": thread_id,
                    "question": intr_value.get("question", ""),
                    "missing_fields": intr_value.get("missing_fields", []),
                }))
                return True
    return False


def _latest_assistant_message(node_output: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            message for message in reversed(node_output.get("messages", []))
            if message.get("role") == "assistant" and message.get("content")
        ),
        None,
    )


def emit_node_events(q: queue.Queue, node_name: str, node_output: dict[str, Any]) -> None:
    label = NODE_LABELS.get(node_name, f"Running {node_name}...")
    q.put(sse_event("node_start", {"node": node_name, "label": label}))
    if node_name == "review":
        return

    latest_message = _latest_assistant_message(node_output)
    if latest_message:
        q.put(sse_event("node_message", {
            "node": node_name,
            "content": latest_message["content"],
        }))


def run_planning_sync(q: queue.Queue, initial_state: dict[str, Any], config: dict[str, Any]) -> None:
    """Run graph.stream() synchronously, pushing SSE-formatted strings to a queue."""
    try:
        graph = get_graph()
        for event in graph.stream(initial_state, config):
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    emit_node_events(q, node_name, node_output)

        state_snapshot = graph.get_state(config)
        thread_id = config["configurable"]["thread_id"]
        if not _emit_clarification_if_present(q, thread_id, state_snapshot):
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(sse_event("state", merged))
    except Exception as exc:
        logger.exception("Planning stream failed")
        q.put(sse_event("error", {"detail": str(exc)}))
    finally:
        q.put(SENTINEL)


def run_post_review_sync(q: queue.Queue, thread_id: str, state_updates: dict[str, Any]) -> None:
    """Resume the graph after review, supporting approval or plan revision."""
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        with token_emitter_context(lambda chunk: q.put(sse_event("token", {"content": chunk}))):
            for event in graph.stream(Command(resume=state_updates), config):
                for node_name, node_output in event.items():
                    if not isinstance(node_output, dict):
                        continue
                    emit_node_events(q, node_name, node_output)

        state_snapshot = graph.get_state(config)
        if not _emit_clarification_if_present(q, thread_id, state_snapshot):
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(sse_event("state", merged))
    except Exception as exc:
        logger.exception("Post-review stream failed")
        q.put(sse_event("error", {"detail": str(exc)}))
    finally:
        q.put(SENTINEL)


def run_clarification_sync(q: queue.Queue, thread_id: str, answer: str) -> None:
    """Resume the graph after a clarification interrupt, pushing SSE events to a queue."""
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        for event in graph.stream(Command(resume=answer), config):
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    emit_node_events(q, node_name, node_output)

        state_snapshot = graph.get_state(config)
        if not _emit_clarification_if_present(q, thread_id, state_snapshot):
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(sse_event("state", merged))
    except Exception as exc:
        logger.exception("Clarification stream failed")
        q.put(sse_event("error", {"detail": str(exc)}))
    finally:
        q.put(SENTINEL)


async def queue_to_sse(q: queue.Queue):
    """Async generator that drains a queue and yields SSE strings."""
    loop = asyncio.get_event_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is SENTINEL:
            yield sse_event("done", {})
            break
        yield item
