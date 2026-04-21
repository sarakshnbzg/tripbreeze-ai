"""FastAPI backend — exposes the LangGraph travel-planning pipeline over HTTP + SSE.

Dependency direction: presentation.api -> application -> domain -> infrastructure
This module imports from the application layer (graph, state) and domain (flight agent).
"""

import asyncio
import json
import queue
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from langgraph.types import Command

from application.graph import compile_graph
from config import (
    FRONTEND_ORIGINS,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_SENDER_EMAIL,
    SMTP_SENDER_PASSWORD,
    SMTP_USE_TLS,
)
from domain.agents.flight_agent import fetch_return_flights
from infrastructure.email_sender import SMTPConfig, send_itinerary_email
from infrastructure.logging_utils import get_logger
from infrastructure.llms.model_factory import get_provider_status
from infrastructure.persistence.memory_store import (
    list_reference_values,
    load_profile,
    register_user,
    save_profile,
    verify_user,
)
from infrastructure.pdf_generator import generate_trip_pdf

logger = get_logger(__name__)

app = FastAPI(title="TripBreeze API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=4)

# Lazy-initialised graph (thread-safe via LangGraph's compiled graph)
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = compile_graph()
    return _graph


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Lightweight container/lb health endpoint."""
    return {"status": "ok"}


# ── SSE helpers ──

_SENTINEL = object()

NODE_LABELS = {
    "load_profile": "Loading your traveler profile...",
    "trip_intake": "Understanding your trip request...",
    "research": "Researching flights, hotels, and destination info...",
    "aggregate_budget": "Calculating budget breakdown...",
    "review": "Preparing your trip summary...",
    "feedback_router": "Updating the workflow based on your decision...",
    "attractions": "Finding attractions for your itinerary...",
    "finalise": "Finalising your itinerary...",
    "update_memory": "Saving your travel preferences...",
}


def _sse_event(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _iter_text_chunks(text: str):
    for chunk in re.split(r"(\s+)", text):
        if chunk:
            yield chunk


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
    feedback_type: str = "rewrite_itinerary"
    # Legacy single-selection (backward compat)
    selected_flight: dict[str, Any] = {}
    selected_hotel: dict[str, Any] = {}
    selected_transport: dict[str, Any] = {}
    # Multi-city selections (one per leg)
    selected_flights: list[dict[str, Any]] = []
    selected_hotels: list[dict[str, Any]] = []
    trip_request: dict[str, Any] | None = None
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


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    profile: dict[str, Any] | None = None


class SaveProfileRequest(BaseModel):
    profile: dict[str, Any]


class ItineraryPdfRequest(BaseModel):
    final_itinerary: str
    graph_state: dict[str, Any] | None = None
    file_name: str = "trip_itinerary.pdf"


class ItineraryEmailRequest(BaseModel):
    recipient_email: str
    recipient_name: str = ""
    final_itinerary: str
    graph_state: dict[str, Any] | None = None


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


def _emit_node_events(q: queue.Queue, node_name: str, node_output: dict) -> None:
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


def _run_post_review_sync(q: queue.Queue, thread_id: str, state_updates: dict) -> None:
    """Resume the graph after review, supporting approval or plan revision."""
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        for event in graph.stream(Command(resume=state_updates), config):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                _emit_node_events(q, node_name, node_output)

                if node_name == "finalise":
                    itinerary_markdown = str(node_output.get("final_itinerary") or "")
                    for chunk in _iter_text_chunks(itinerary_markdown):
                        q.put(_sse_event("token", {"content": chunk}))

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
        logger.exception("Post-review stream failed")
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


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Validate credentials and return the user's profile."""
    if not req.user_id.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    try:
        authenticated = verify_user(req.user_id.strip(), req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Login failed")
        raise HTTPException(status_code=500, detail=f"Login failed: {exc}") from exc

    if not authenticated:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"user_id": req.user_id.strip(), "profile": load_profile(req.user_id.strip())}


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register a new user and return the created profile."""
    if not req.user_id.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    try:
        created = register_user(req.user_id.strip(), req.password, req.profile or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Registration failed")
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}") from exc

    if not created:
        raise HTTPException(status_code=409, detail="Username is already taken")

    return {"user_id": req.user_id.strip(), "profile": load_profile(req.user_id.strip())}


@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    """Return a user's stored profile."""
    try:
        return {"user_id": user_id, "profile": load_profile(user_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile load failed")
        raise HTTPException(status_code=500, detail=f"Profile load failed: {exc}") from exc


@app.put("/api/profile/{user_id}")
async def update_profile(user_id: str, req: SaveProfileRequest):
    """Persist a user's profile updates."""
    try:
        save_profile(user_id, req.profile)
        return {"user_id": user_id, "profile": load_profile(user_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile save failed")
        raise HTTPException(status_code=500, detail=f"Profile save failed: {exc}") from exc


@app.get("/api/reference-values/{category}")
async def reference_values(category: str):
    """Return reference values such as cities, countries, and airlines."""
    try:
        return {"category": category, "values": list_reference_values(category)}
    except Exception as exc:
        logger.exception("Reference values load failed")
        raise HTTPException(status_code=500, detail=f"Reference values load failed: {exc}") from exc


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
        "feedback_type": "rewrite_itinerary",
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
        "user_approved": req.feedback_type != "revise_plan",
        "user_feedback": req.user_feedback,
        "feedback_type": req.feedback_type,
        "llm_provider": req.llm_provider,
        "llm_model": req.llm_model,
        "llm_temperature": req.llm_temperature,
    }

    # Multi-city takes precedence over legacy single-selection
    if req.selected_flights:
        state_updates["selected_flights"] = req.selected_flights
        state_updates["selected_hotels"] = req.selected_hotels
        # Backward compat: populate legacy fields with first leg
        state_updates["selected_flight"] = req.selected_flights[0] if req.selected_flights else {}
        state_updates["selected_hotel"] = req.selected_hotels[0] if req.selected_hotels else {}
    else:
        # Legacy single-selection
        state_updates["selected_flight"] = req.selected_flight
        state_updates["selected_hotel"] = req.selected_hotel
    state_updates["selected_transport"] = req.selected_transport

    if req.trip_request:
        state_updates["trip_request"] = req.trip_request
    if req.user_feedback.strip():
        prefix = "Please revise this plan: " if req.feedback_type == "revise_plan" else "Final itinerary notes: "
        state_updates["messages"] = [{"role": "user", "content": f"{prefix}{req.user_feedback.strip()}"}]

    q: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_post_review_sync, q, thread_id, state_updates)

    return StreamingResponse(
        _queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/itinerary/pdf")
async def itinerary_pdf(req: ItineraryPdfRequest):
    """Generate a PDF for a final itinerary."""
    if not req.final_itinerary.strip():
        raise HTTPException(status_code=400, detail="Final itinerary is required")

    try:
        pdf_bytes = generate_trip_pdf(
            final_itinerary=req.final_itinerary,
            graph_state=req.graph_state or {},
        )
    except Exception as exc:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{req.file_name or "trip_itinerary.pdf"}"'},
    )


@app.post("/api/itinerary/email")
async def itinerary_email(req: ItineraryEmailRequest):
    """Email the itinerary PDF to a recipient."""
    if not req.recipient_email.strip():
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not req.final_itinerary.strip():
        raise HTTPException(status_code=400, detail="Final itinerary is required")

    try:
        pdf_bytes = generate_trip_pdf(
            final_itinerary=req.final_itinerary,
            graph_state=req.graph_state or {},
        )
        smtp_config = SMTPConfig(
            smtp_host=SMTP_HOST,
            smtp_port=SMTP_PORT,
            sender_email=SMTP_SENDER_EMAIL,
            sender_password=SMTP_SENDER_PASSWORD,
            use_tls=SMTP_USE_TLS,
        )
        success, message = send_itinerary_email(
            recipient_email=req.recipient_email.strip(),
            pdf_bytes=pdf_bytes,
            smtp_config=smtp_config,
            recipient_name=req.recipient_name.strip() or "traveler",
        )
    except Exception as exc:
        logger.exception("Itinerary email failed")
        raise HTTPException(status_code=500, detail=f"Itinerary email failed: {exc}") from exc

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}
