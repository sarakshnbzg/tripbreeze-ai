"""Session authentication helpers for the FastAPI backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Final

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from settings import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
)

SESSION_COOKIE_PATH: Final[str] = "/"
SESSION_COOKIE_SAMESITE: Final[str] = "lax"
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


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _sign(payload: str) -> str:
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(signature)


def create_session_token(user_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + SESSION_MAX_AGE_SECONDS,
    }
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{encoded_payload}.{_sign(encoded_payload)}"


def verify_session_token(token: str) -> str | None:
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = _sign(encoded_payload)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    user_id = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(user_id, str) or not user_id.strip():
        return None
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    return user_id


def set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user_id),
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


def get_authenticated_user(request: Request) -> str:
    user_id = getattr(request.state, "authenticated_user", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def ensure_user_access(requested_user_id: str, authenticated_user_id: str) -> None:
    if requested_user_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="You may only access your own profile")


def extract_session_user(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return verify_session_token(auth_header[7:].strip())

    session_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
    if session_cookie:
        return verify_session_token(session_cookie)
    return None


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
