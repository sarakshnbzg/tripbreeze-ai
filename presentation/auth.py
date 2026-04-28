"""Session authentication helpers for the FastAPI backend."""

from __future__ import annotations

from typing import Final

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from infrastructure.persistence.memory_store import (
    create_user_session,
    delete_user_session,
    get_user_for_session,
)
from settings import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_IDLE_TIMEOUT_SECONDS,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
)

SESSION_COOKIE_PATH: Final[str] = "/"
SESSION_COOKIE_SAMESITE: Final[str] = "strict"
PUBLIC_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "/docs",
    "/openapi.json",
    "/redoc",
    "/healthz",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/logout",
    "/api/reference-values/",
)

def create_session_token(user_id: str) -> str:
    return create_user_session(
        user_id,
        SESSION_MAX_AGE_SECONDS,
        idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS,
        rotate_existing=False,
    )


def verify_session_token(token: str) -> str | None:
    return get_user_for_session(token, idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS)


def set_session_cookie(response: Response, user_id: str) -> None:
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET must be configured before issuing session cookies")
    session_token = create_user_session(
        user_id,
        SESSION_MAX_AGE_SECONDS,
        idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS,
        rotate_existing=True,
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        max_age=SESSION_MAX_AGE_SECONDS,
        path=SESSION_COOKIE_PATH,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=SESSION_COOKIE_PATH,
        samesite=SESSION_COOKIE_SAMESITE,
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
    )


def extract_session_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.cookies.get(SESSION_COOKIE_NAME, "").strip()


def invalidate_session_token(token: str) -> None:
    delete_user_session(token)


def get_authenticated_user(request: Request) -> str:
    user_id = getattr(request.state, "authenticated_user", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def ensure_user_access(requested_user_id: str, authenticated_user_id: str) -> None:
    if requested_user_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="You may only access your own profile")


def extract_session_user(request: Request) -> str | None:
    session_token = extract_session_token(request)
    if not session_token:
        return None
    return verify_session_token(session_token)


def is_public_path(path: str) -> bool:
    if path in {"/api/auth/login", "/api/auth/register", "/api/auth/logout", "/healthz", "/openapi.json", "/docs", "/redoc"}:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or is_public_path(request.url.path):
        return await call_next(request)

    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    authenticated_user = extract_session_user(request)
    if not authenticated_user:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    request.state.authenticated_user = authenticated_user
    return await call_next(request)
