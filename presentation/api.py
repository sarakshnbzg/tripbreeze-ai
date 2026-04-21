"""FastAPI backend — exposes the LangGraph travel-planning pipeline over HTTP + SSE.

Dependency direction: presentation.api -> application -> domain -> infrastructure
This module now assembles routers and re-exports key helpers used by tests.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import FRONTEND_ORIGINS
from presentation import (
    api_routes_auth,
    api_routes_itinerary,
    api_routes_planning,
    api_routes_system,
)
from presentation.api_models import (
    ApproveRequest,
    ClarifyRequest,
    ItineraryEmailRequest,
    ItineraryPdfRequest,
    LoginRequest,
    RegisterRequest,
    ReturnFlightRequest,
    SaveProfileRequest,
    SearchRequest,
)
from presentation.api_runtime import executor as _executor
from presentation.api_runtime import get_graph as _get_graph
from presentation.api_sse import (
    emit_node_events as _emit_node_events,
    queue_to_sse as _queue_to_sse,
    run_clarification_sync as _run_clarification_sync,
    run_planning_sync as _run_planning_sync,
    run_post_review_sync as _run_post_review_sync,
    sse_event as _sse_event,
)

app = FastAPI(title="TripBreeze API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_routes_system.router)
app.include_router(api_routes_auth.router)
app.include_router(api_routes_planning.router)
app.include_router(api_routes_itinerary.router)
