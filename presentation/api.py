"""FastAPI backend — exposes the LangGraph travel-planning pipeline over HTTP + SSE.

Dependency direction: presentation.api -> application -> domain -> infrastructure
This module imports from the application layer (graph, state) and domain (flight agent).
"""

import asyncio
import json
import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langgraph.types import Command

from application.graph import compile_graph, run_finalisation_streaming
from domain.agents.flight_agent import fetch_return_flights
from infrastructure.logging_utils import get_logger
from infrastructure.llms.model_factory import get_provider_status

logger = get_logger(__name__)

app = FastAPI(title="TripBreeze API")

_executor = ThreadPoolExecutor(max_workers=4)

# Lazy-initialised graph (thread-safe via LangGraph's compiled graph)
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = compile_graph()
    return _graph


# ── SSE helpers ──

_SENTINEL = object()

NODE_LABELS = {
    "load_profile": "Loading your traveler profile...",
    "trip_intake": "Understanding your trip request...",
    "research": "Researching flights, hotels, and destination info...",
    "aggregate_budget": "Calculating budget breakdown...",
    "review": "Preparing your trip summary...",
}


def _sse_event(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


# ── Request / Response models ──

class SearchRequest(BaseModel):
    user_id: str = "default_user"
    free_text_query: str | None = None
    structured_fields: dict[str, Any] | None = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3


class ApproveRequest(BaseModel):
    user_feedback: str = ""
    selected_flight: dict[str, Any] = {}
    selected_hotel: dict[str, Any] = {}
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3


class ClarifyRequest(BaseModel):
    answer: str


class ReturnFlightRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: str
    departure_token: str
    adults: int = 1
    travel_class: str = "ECONOMY"
    currency: str = "EUR"
    return_time_window: list[int] | None = None


# ── Streaming bridges (sync graph -> async SSE) ──

def _run_planning_sync(q: queue.Queue, initial_state: dict, config: dict) -> None:
    """Run graph.stream() synchronously, pushing SSE-formatted strings to a queue."""
    try:
        graph = _get_graph()
        result = initial_state.copy()
        for event in graph.stream(initial_state, config):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                label = NODE_LABELS.get(node_name, f"Running {node_name}...")
                q.put(_sse_event("node_start", {"node": node_name, "label": label}))

                if node_name != "review":
                    latest_message = next(
                        (
                            m for m in reversed(node_output.get("messages", []))
                            if m.get("role") == "assistant" and m.get("content")
                        ),
                        None,
                    )
                    if latest_message:
                        q.put(_sse_event("node_message", {
                            "node": node_name,
                            "content": latest_message["content"],
                        }))
                result.update(node_output)

        # Check if the graph paused for a clarification interrupt
        state_snapshot = graph.get_state(config)
        has_interrupt = False
        for task in (state_snapshot.tasks or []):
            for intr in (task.interrupts or []):
                intr_value = intr.value if hasattr(intr, "value") else intr
                if isinstance(intr_value, dict) and intr_value.get("type") == "clarification":
                    q.put(_sse_event("clarification", {
                        "thread_id": config["configurable"]["thread_id"],
                        "question": intr_value.get("question", ""),
                        "missing_fields": intr_value.get("missing_fields", []),
                    }))
                    has_interrupt = True
                    break
            if has_interrupt:
                break

        if not has_interrupt:
            # Authoritative merged state from checkpointer
            merged = dict(state_snapshot.values)
            merged["thread_id"] = config["configurable"]["thread_id"]
            q.put(_sse_event("state", merged))
    except Exception as exc:
        logger.exception("Planning stream failed")
        q.put(_sse_event("error", {"detail": str(exc)}))
    finally:
        q.put(_SENTINEL)


def _run_finalisation_sync(q: queue.Queue, thread_id: str, state_updates: dict) -> None:
    """Run finalisation streaming synchronously, pushing SSE events to a queue."""
    try:
        graph = _get_graph()
        for item in run_finalisation_streaming(graph, thread_id, state_updates):
            if isinstance(item, str):
                q.put(_sse_event("token", {"content": item}))
            else:
                # Final state dict
                item["thread_id"] = thread_id
                q.put(_sse_event("state", item))
    except Exception as exc:
        logger.exception("Finalisation stream failed")
        q.put(_sse_event("error", {"detail": str(exc)}))
    finally:
        q.put(_SENTINEL)


def _run_clarification_sync(q: queue.Queue, thread_id: str, answer: str) -> None:
    """Resume the graph after a clarification interrupt, pushing SSE events to a queue."""
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        result: dict = {}
        for event in graph.stream(Command(resume=answer), config):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                label = NODE_LABELS.get(node_name, f"Running {node_name}...")
                q.put(_sse_event("node_start", {"node": node_name, "label": label}))

                if node_name != "review":
                    latest_message = next(
                        (
                            m for m in reversed(node_output.get("messages", []))
                            if m.get("role") == "assistant" and m.get("content")
                        ),
                        None,
                    )
                    if latest_message:
                        q.put(_sse_event("node_message", {
                            "node": node_name,
                            "content": latest_message["content"],
                        }))
                result.update(node_output)

        # Check if there's another clarification interrupt (still missing fields)
        state_snapshot = graph.get_state(config)
        has_interrupt = False
        for task in (state_snapshot.tasks or []):
            for intr in (task.interrupts or []):
                intr_value = intr.value if hasattr(intr, "value") else intr
                if isinstance(intr_value, dict) and intr_value.get("type") == "clarification":
                    q.put(_sse_event("clarification", {
                        "thread_id": thread_id,
                        "question": intr_value.get("question", ""),
                        "missing_fields": intr_value.get("missing_fields", []),
                    }))
                    has_interrupt = True
                    break
            if has_interrupt:
                break

        if not has_interrupt:
            merged = dict(state_snapshot.values)
            merged["thread_id"] = thread_id
            q.put(_sse_event("state", merged))
    except Exception as exc:
        logger.exception("Clarification stream failed")
        q.put(_sse_event("error", {"detail": str(exc)}))
    finally:
        q.put(_SENTINEL)


async def _queue_to_sse(q: queue.Queue):
    """Async generator that drains a queue and yields SSE strings."""
    loop = asyncio.get_event_loop()
    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is _SENTINEL:
            yield _sse_event("done", {})
            break
        yield item


# ── Endpoints ──

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Transcribe audio to text using OpenAI Whisper."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        import openai
        client = openai.OpenAI()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename or "audio.wav", audio_bytes),
        )
        return {"text": transcript.text}
    except Exception as exc:
        logger.exception("Whisper transcription failed")
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")


@app.post("/api/search")
async def search(req: SearchRequest):
    """Start trip planning. Returns an SSE stream of progress events."""
    provider_ready, provider_message = get_provider_status(req.llm_provider)
    if not provider_ready:
        raise HTTPException(status_code=400, detail=provider_message)

    thread_id = str(uuid.uuid4())
    initial_state: dict[str, Any] = {
        "user_id": req.user_id,
        "llm_provider": req.llm_provider,
        "llm_model": req.llm_model,
        "llm_temperature": req.llm_temperature,
        "messages": [{"role": "user", "content": req.free_text_query or ""}],
        "user_approved": False,
        "user_feedback": "",
    }
    if req.structured_fields:
        initial_state["structured_fields"] = req.structured_fields
    if req.free_text_query:
        initial_state["free_text_query"] = req.free_text_query

    config = {"configurable": {"thread_id": thread_id}}

    q: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_planning_sync, q, initial_state, config)

    return StreamingResponse(
        _queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/search/{thread_id}/state")
async def get_state(thread_id: str):
    """Return the current graph state for a given thread (used for HITL review)."""
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found")
    result = dict(state_snapshot.values)
    result["thread_id"] = thread_id
    return result


@app.post("/api/search/{thread_id}/return-flights")
async def return_flights(thread_id: str, req: ReturnFlightRequest):
    """Fetch return flight options for a selected outbound departure token."""
    loop = asyncio.get_event_loop()
    time_window = tuple(req.return_time_window) if req.return_time_window and len(req.return_time_window) == 2 else None
    results = await loop.run_in_executor(
        _executor,
        lambda: fetch_return_flights(
            origin=req.origin,
            destination=req.destination,
            departure_date=req.departure_date,
            return_date=req.return_date,
            departure_token=req.departure_token,
            adults=req.adults,
            travel_class=req.travel_class,
            currency=req.currency,
            return_time_window=time_window,
        ),
    )
    return results


@app.post("/api/search/{thread_id}/clarify")
async def clarify(thread_id: str, req: ClarifyRequest):
    """Resume trip planning after the user answers a clarification question. Returns an SSE stream."""
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    q: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_clarification_sync, q, thread_id, req.answer.strip())

    return StreamingResponse(
        _queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/search/{thread_id}/approve")
async def approve(thread_id: str, req: ApproveRequest):
    """Approve HITL selections and stream the final itinerary via SSE."""
    provider_ready, provider_message = get_provider_status(req.llm_provider)
    if not provider_ready:
        raise HTTPException(status_code=400, detail=provider_message)

    state_updates = {
        "user_approved": True,
        "user_feedback": req.user_feedback,
        "selected_flight": req.selected_flight,
        "selected_hotel": req.selected_hotel,
        "llm_provider": req.llm_provider,
        "llm_model": req.llm_model,
        "llm_temperature": req.llm_temperature,
    }

    q: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_finalisation_sync, q, thread_id, state_updates)

    return StreamingResponse(
        _queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
