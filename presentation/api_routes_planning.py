"""Planner and HITL review routes for the FastAPI backend."""

import asyncio
import queue
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from domain.agents.flight_agent import fetch_return_flights
from infrastructure.llms.model_factory import get_provider_status
from presentation.api_models import ApproveRequest, ClarifyRequest, ReturnFlightRequest, SearchRequest
from presentation.api_runtime import executor, get_graph
from presentation.api_sse import queue_to_sse, run_clarification_sync, run_planning_sync, run_post_review_sync

router = APIRouter()


@router.post("/api/search")
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
    asyncio.get_event_loop().run_in_executor(executor, run_planning_sync, q, initial_state, config)

    return StreamingResponse(
        queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/search/{thread_id}/state")
async def get_state(thread_id: str):
    """Return the current graph state for a given thread (used for HITL review)."""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found")
    result = dict(state_snapshot.values)
    result["thread_id"] = thread_id
    return result


@router.post("/api/search/{thread_id}/return-flights")
async def return_flights(thread_id: str, req: ReturnFlightRequest):
    """Fetch return flight options for a selected outbound departure token."""
    time_window = tuple(req.return_time_window) if req.return_time_window and len(req.return_time_window) == 2 else None
    results = await asyncio.get_event_loop().run_in_executor(
        executor,
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


@router.post("/api/search/{thread_id}/clarify")
async def clarify(thread_id: str, req: ClarifyRequest):
    """Resume trip planning after the user answers a clarification question. Returns an SSE stream."""
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    q: queue.Queue = queue.Queue()
    asyncio.get_event_loop().run_in_executor(executor, run_clarification_sync, q, thread_id, req.answer.strip())

    return StreamingResponse(
        queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/search/{thread_id}/approve")
async def approve(thread_id: str, req: ApproveRequest):
    """Approve HITL selections and stream the final itinerary via SSE."""
    provider_ready, provider_message = get_provider_status(req.llm_provider)
    if not provider_ready:
        raise HTTPException(status_code=400, detail=provider_message)

    state_updates: dict[str, Any] = {
        "user_approved": req.feedback_type != "revise_plan",
        "user_feedback": req.user_feedback,
        "feedback_type": req.feedback_type,
        "llm_provider": req.llm_provider,
        "llm_model": req.llm_model,
        "llm_temperature": req.llm_temperature,
    }

    if req.selected_flights:
        state_updates["selected_flights"] = req.selected_flights
        state_updates["selected_hotels"] = req.selected_hotels
        state_updates["selected_flight"] = req.selected_flights[0] if req.selected_flights else {}
        state_updates["selected_hotel"] = req.selected_hotels[0] if req.selected_hotels else {}
    else:
        state_updates["selected_flight"] = req.selected_flight
        state_updates["selected_hotel"] = req.selected_hotel

    if req.trip_request:
        state_updates["trip_request"] = req.trip_request
    if req.user_feedback.strip():
        prefix = "Please revise this plan: " if req.feedback_type == "revise_plan" else "Final itinerary notes: "
        state_updates["messages"] = [{"role": "user", "content": f"{prefix}{req.user_feedback.strip()}"}]

    q: queue.Queue = queue.Queue()
    asyncio.get_event_loop().run_in_executor(executor, run_post_review_sync, q, thread_id, state_updates)

    return StreamingResponse(
        queue_to_sse(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
