"""Auth, profile, and reference-value routes for the FastAPI backend."""

from collections import deque
from threading import Lock
import time

from fastapi import APIRouter, HTTPException, Request, Response

from infrastructure.persistence.memory_store import (
    list_reference_values,
    load_profile,
    register_user,
    save_profile,
    verify_user,
)
from presentation.api_security import log_and_raise_api_error
from presentation.auth import (
    clear_session_cookie,
    ensure_user_access,
    extract_session_token,
    get_authenticated_csrf_token,
    get_authenticated_user,
    invalidate_session_token,
    set_session_cookie,
)
from presentation.api_models import LoginRequest, RegisterRequest, SaveProfileRequest
from presentation.api_runtime import logger

router = APIRouter()

_AUTH_RATE_LIMIT_WINDOW_SECONDS = 300
_AUTH_RATE_LIMIT_MAX_ATTEMPTS = 10
_AUTH_ATTEMPTS: dict[tuple[str, str], deque[float]] = {}
_AUTH_ATTEMPTS_LOCK = Lock()


def _client_address(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for.strip():
        return forwarded_for.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", "")
    return str(host or "unknown")


def _auth_rate_limit_key(action: str, request: Request) -> tuple[str, str]:
    return action, _client_address(request)


def _enforce_auth_rate_limit(action: str, request: Request) -> None:
    now = time.monotonic()
    key = _auth_rate_limit_key(action, request)
    with _AUTH_ATTEMPTS_LOCK:
        attempts = _AUTH_ATTEMPTS.setdefault(key, deque())
        while attempts and now - attempts[0] > _AUTH_RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _AUTH_RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts. Please wait a few minutes and try again.",
            )
        attempts.append(now)


def _clear_auth_rate_limit(action: str, request: Request) -> None:
    key = _auth_rate_limit_key(action, request)
    with _AUTH_ATTEMPTS_LOCK:
        _AUTH_ATTEMPTS.pop(key, None)


@router.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Validate credentials and return the user's profile."""
    if not req.user_id.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    _enforce_auth_rate_limit("login", request)

    try:
        authenticated = verify_user(req.user_id.strip(), req.password)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid login request.") from exc
    except Exception as exc:
        log_and_raise_api_error(
            event="api.login_failed",
            public_message="Login failed. Please try again later.",
            exc=exc,
            status_code=500,
            path="/api/auth/login",
            user_id=req.user_id.strip(),
        )

    if not authenticated:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_id = req.user_id.strip()
    _clear_auth_rate_limit("login", request)
    csrf_token = set_session_cookie(response, user_id)
    return {"user_id": user_id, "profile": load_profile(user_id), "csrf_token": csrf_token}


@router.post("/api/auth/register")
async def register(req: RegisterRequest, request: Request, response: Response):
    """Register a new user and return the created profile."""
    if not req.user_id.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    _enforce_auth_rate_limit("register", request)

    try:
        created = register_user(req.user_id.strip(), req.password, req.profile or {})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid registration details.") from exc
    except Exception as exc:
        log_and_raise_api_error(
            event="api.registration_failed",
            public_message="Registration failed. Please try again later.",
            exc=exc,
            status_code=500,
            path="/api/auth/register",
            user_id=req.user_id.strip(),
        )

    if not created:
        raise HTTPException(status_code=409, detail="Username is already taken")

    user_id = req.user_id.strip()
    _clear_auth_rate_limit("register", request)
    csrf_token = set_session_cookie(response, user_id)
    return {"user_id": user_id, "profile": load_profile(user_id), "csrf_token": csrf_token}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """Clear the current session cookie."""
    session_token = extract_session_token(request)
    if session_token:
        invalidate_session_token(session_token)
    clear_session_cookie(response)
    return {"success": True}


@router.get("/api/profile/{user_id}")
async def get_profile(user_id: str, request: Request):
    """Return a user's stored profile."""
    try:
        ensure_user_access(user_id, get_authenticated_user(request))
        return {
            "user_id": user_id,
            "profile": load_profile(user_id),
            "csrf_token": get_authenticated_csrf_token(request),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid profile request.") from exc
    except Exception as exc:
        log_and_raise_api_error(
            event="api.profile_load_failed",
            public_message="Profile load failed. Please try again later.",
            exc=exc,
            status_code=500,
            path="/api/profile/{user_id}",
            user_id=user_id,
        )


@router.put("/api/profile/{user_id}")
async def update_profile(user_id: str, req: SaveProfileRequest, request: Request):
    """Persist a user's profile updates."""
    try:
        ensure_user_access(user_id, get_authenticated_user(request))
        save_profile(user_id, req.profile)
        return {
            "user_id": user_id,
            "profile": load_profile(user_id),
            "csrf_token": get_authenticated_csrf_token(request),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid profile update request.") from exc
    except Exception as exc:
        log_and_raise_api_error(
            event="api.profile_save_failed",
            public_message="Profile save failed. Please try again later.",
            exc=exc,
            status_code=500,
            path="/api/profile/{user_id}",
            user_id=user_id,
        )


@router.get("/api/reference-values/{category}")
async def reference_values(category: str):
    """Return reference values such as cities, countries, and airlines."""
    try:
        return {"category": category, "values": list_reference_values(category)}
    except Exception as exc:
        log_and_raise_api_error(
            event="api.reference_values_failed",
            public_message="Reference values are temporarily unavailable.",
            exc=exc,
            status_code=500,
            path="/api/reference-values/{category}",
            category=category,
        )
