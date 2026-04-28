"""SSE helpers and sync-to-async graph bridges for the FastAPI backend."""

import asyncio
import json
import queue
import time
from typing import Any

from langgraph.types import Command

from infrastructure.streaming import token_emitter_context
from infrastructure.logging_utils import log_event
from presentation.api_runtime import NODE_LABELS, get_graph, logger

SENTINEL = object()


def sse_event(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _emit_clarification_if_present(q: queue.Queue, thread_id: str, state_snapshot: Any) -> bool:
    for task in (getattr(state_snapshot, "tasks", None) or []):
        for intr in (getattr(task, "interrupts", None) or []):
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


def _token_usage_summary(entries: list[dict[str, Any]] | None) -> dict[str, float | int]:
    usage_entries = entries or []
    return {
        "llm_calls": len(usage_entries),
        "input_tokens": sum(int(entry.get("input_tokens", 0) or 0) for entry in usage_entries),
        "output_tokens": sum(int(entry.get("output_tokens", 0) or 0) for entry in usage_entries),
        "cost_usd": round(sum(float(entry.get("cost_usd", entry.get("cost", 0)) or 0) for entry in usage_entries), 6),
    }


def _log_step_observability(
    *,
    thread_id: str,
    node_name: str,
    node_output: dict[str, Any],
    elapsed_ms: float,
) -> None:
    usage = _token_usage_summary(node_output.get("token_usage"))
    log_event(
        logger,
        "workflow.step_completed",
        thread_id=thread_id,
        step=node_name,
        latency_ms=round(elapsed_ms, 2),
        llm_calls=usage["llm_calls"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=usage["cost_usd"],
        message_count=len(node_output.get("messages", []) or []),
        node_error_count=len(node_output.get("node_errors", []) or []),
        current_step=str(node_output.get("current_step", "") or ""),
    )


def _log_run_summary(*, thread_id: str, state_values: dict[str, Any], event_name: str, total_elapsed_ms: float) -> None:
    usage = _token_usage_summary(state_values.get("token_usage"))
    log_event(
        logger,
        event_name,
        thread_id=thread_id,
        total_latency_ms=round(total_elapsed_ms, 2),
        llm_calls=usage["llm_calls"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=usage["cost_usd"],
        current_step=str(state_values.get("current_step", "") or ""),
        has_final_itinerary=bool(state_values.get("final_itinerary")),
        node_error_count=len(state_values.get("node_errors", []) or []),
    )


def run_planning_sync(q: queue.Queue, initial_state: dict[str, Any], config: dict[str, Any]) -> None:
    """Run graph.stream() synchronously, pushing SSE-formatted strings to a queue."""
    thread_id = config["configurable"]["thread_id"]
    run_started_at = time.perf_counter()
    last_event_at = run_started_at
    try:
        graph = get_graph()
        for event in graph.stream(initial_state, config):
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    now = time.perf_counter()
                    emit_node_events(q, node_name, node_output)
                    _log_step_observability(
                        thread_id=thread_id,
                        node_name=node_name,
                        node_output=node_output,
                        elapsed_ms=(now - last_event_at) * 1000,
                    )
                    last_event_at = now

        state_snapshot = graph.get_state(config)
        if not _emit_clarification_if_present(q, thread_id, state_snapshot):
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(sse_event("state", merged))
            _log_run_summary(
                thread_id=thread_id,
                state_values=merged,
                event_name="workflow.run_completed",
                total_elapsed_ms=(time.perf_counter() - run_started_at) * 1000,
            )
    except Exception as exc:
        logger.exception("Planning stream failed")
        q.put(sse_event("error", {"detail": str(exc)}))
        log_event(
            logger,
            "workflow.run_failed",
            thread_id=thread_id,
            total_latency_ms=round((time.perf_counter() - run_started_at) * 1000, 2),
            error_type=type(exc).__name__,
        )
    finally:
        q.put(SENTINEL)


def run_post_review_sync(q: queue.Queue, thread_id: str, state_updates: dict[str, Any]) -> None:
    """Resume the graph after review, supporting approval or plan revision."""
    run_started_at = time.perf_counter()
    last_event_at = run_started_at
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        with token_emitter_context(lambda chunk: q.put(sse_event("token", {"content": chunk}))):
            for event in graph.stream(Command(resume=state_updates), config):
                for node_name, node_output in event.items():
                    if not isinstance(node_output, dict):
                        continue
                    now = time.perf_counter()
                    emit_node_events(q, node_name, node_output)
                    _log_step_observability(
                        thread_id=thread_id,
                        node_name=node_name,
                        node_output=node_output,
                        elapsed_ms=(now - last_event_at) * 1000,
                    )
                    last_event_at = now

        state_snapshot = graph.get_state(config)
        if not _emit_clarification_if_present(q, thread_id, state_snapshot):
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(sse_event("state", merged))
            _log_run_summary(
                thread_id=thread_id,
                state_values=merged,
                event_name="workflow.post_review_completed",
                total_elapsed_ms=(time.perf_counter() - run_started_at) * 1000,
            )
    except Exception as exc:
        logger.exception("Post-review stream failed")
        q.put(sse_event("error", {"detail": str(exc)}))
        log_event(
            logger,
            "workflow.post_review_failed",
            thread_id=thread_id,
            total_latency_ms=round((time.perf_counter() - run_started_at) * 1000, 2),
            error_type=type(exc).__name__,
        )
    finally:
        q.put(SENTINEL)


def run_clarification_sync(q: queue.Queue, thread_id: str, answer: str) -> None:
    """Resume the graph after a clarification interrupt, pushing SSE events to a queue."""
    run_started_at = time.perf_counter()
    last_event_at = run_started_at
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        for event in graph.stream(Command(resume=answer), config):
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    now = time.perf_counter()
                    emit_node_events(q, node_name, node_output)
                    _log_step_observability(
                        thread_id=thread_id,
                        node_name=node_name,
                        node_output=node_output,
                        elapsed_ms=(now - last_event_at) * 1000,
                    )
                    last_event_at = now

        state_snapshot = graph.get_state(config)
        if not _emit_clarification_if_present(q, thread_id, state_snapshot):
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(sse_event("state", merged))
            _log_run_summary(
                thread_id=thread_id,
                state_values=merged,
                event_name="workflow.clarification_completed",
                total_elapsed_ms=(time.perf_counter() - run_started_at) * 1000,
            )
    except Exception as exc:
        logger.exception("Clarification stream failed")
        q.put(sse_event("error", {"detail": str(exc)}))
        log_event(
            logger,
            "workflow.clarification_failed",
            thread_id=thread_id,
            total_latency_ms=round((time.perf_counter() - run_started_at) * 1000, 2),
            error_type=type(exc).__name__,
        )
    finally:
        q.put(SENTINEL)


async def queue_to_sse(q: queue.Queue):
    """Async generator that drains a queue and yields SSE strings."""
    loop = asyncio.get_running_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is SENTINEL:
            yield sse_event("done", {})
            break
        yield item
