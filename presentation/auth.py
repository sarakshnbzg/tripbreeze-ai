"""Session authentication helpers for the FastAPI backend."""

from __future__ import annotations

from typing import Final
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from infrastructure.persistence.memory_store import (
    create_user_session,
    delete_user_session,
    get_csrf_token_for_session,
    get_session_details,
    get_user_for_session,
)
from settings import (
    API_BASE_URL,
    FRONTEND_ORIGINS,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_IDLE_TIMEOUT_SECONDS,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
)

SESSION_COOKIE_PATH: Final[str] = "/"
SESSION_COOKIE_SAMESITE: Final[str] = "strict"
CSRF_HEADER_NAME: Final[str] = "x-csrf-token"
SAFE_METHODS: Final[set[str]] = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "/docs",
    "/openapi.json",
    "/redoc",
    "/healthz",
    "/api/auth/login",
    "/api/auth/register",
    "/api/reference-values/",
)


def _canonical_origin(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".lower()


ALLOWED_BROWSER_ORIGINS: Final[set[str]] = {
    origin for origin in (
        _canonical_origin(API_BASE_URL),
        *(_canonical_origin(origin) for origin in FRONTEND_ORIGINS),
    ) if origin
}

def create_session_token(user_id: str) -> str:
    session_token, _csrf_token = create_user_session(
        user_id,
        SESSION_MAX_AGE_SECONDS,
        idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS,
        rotate_existing=False,
    )
    return session_token


def verify_session_token(token: str) -> str | None:
    return get_user_for_session(token, idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS)


def set_session_cookie(response: Response, user_id: str) -> None:
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET must be configured before issuing session cookies")
    session_token, csrf_token = create_user_session(
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
    return csrf_token


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


def extract_csrf_token(request: Request) -> str:
    return str(request.headers.get(CSRF_HEADER_NAME, "")).strip()


def get_session_csrf_token(session_token: str) -> str | None:
    return get_csrf_token_for_session(
        session_token,
        idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS,
    )


def get_authenticated_csrf_token(request: Request) -> str:
    csrf_token = str(getattr(request.state, "csrf_token", "")).strip()
    if not csrf_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return csrf_token


def _origin_allowed(value: str) -> bool:
    canonical = _canonical_origin(value)
    return bool(canonical and canonical in ALLOWED_BROWSER_ORIGINS)


def validate_browser_origin(request: Request) -> bool:
    origin = str(request.headers.get("origin", "")).strip()
    referer = str(request.headers.get("referer", "")).strip()
    if origin:
        return _origin_allowed(origin)
    if referer:
        return _origin_allowed(referer)
    return True


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

    session_token = extract_session_token(request)
    if not session_token:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    session_details = get_session_details(
        session_token,
        idle_timeout_seconds=SESSION_IDLE_TIMEOUT_SECONDS,
    )
    if not session_details:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    request.state.authenticated_user = session_details["user_id"]
    request.state.session_token = session_token
    request.state.csrf_token = session_details["csrf_token"]

    if request.method.upper() not in SAFE_METHODS:
        if not validate_browser_origin(request):
            return JSONResponse(status_code=403, content={"detail": "Invalid request origin"})
        csrf_token = extract_csrf_token(request)
        if not csrf_token or csrf_token != session_details["csrf_token"]:
            return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

    return await call_next(request)
