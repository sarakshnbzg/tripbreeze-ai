"""Auth, profile, and reference-value routes for the FastAPI backend."""

from fastapi import APIRouter, HTTPException, Request, Response

from infrastructure.persistence.memory_store import (
    list_reference_values,
    load_profile,
    register_user,
    save_profile,
    verify_user,
)
from presentation.auth import clear_session_cookie, ensure_user_access, get_authenticated_user, set_session_cookie
from presentation.api_models import LoginRequest, RegisterRequest, SaveProfileRequest
from presentation.api_runtime import logger

router = APIRouter()


@router.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    """Validate credentials and return the user's profile."""
    if not req.user_id.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    try:
        authenticated = verify_user(req.user_id.strip(), req.password)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Login failed")
        raise HTTPException(status_code=500, detail=f"Login failed: {exc}") from exc

    if not authenticated:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_id = req.user_id.strip()
    set_session_cookie(response, user_id)
    return {"user_id": user_id, "profile": load_profile(user_id)}


@router.post("/api/auth/register")
async def register(req: RegisterRequest, response: Response):
    """Register a new user and return the created profile."""
    if not req.user_id.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    try:
        created = register_user(req.user_id.strip(), req.password, req.profile or {})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Registration failed")
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}") from exc

    if not created:
        raise HTTPException(status_code=409, detail="Username is already taken")

    user_id = req.user_id.strip()
    set_session_cookie(response, user_id)
    return {"user_id": user_id, "profile": load_profile(user_id)}


@router.post("/api/auth/logout")
async def logout(response: Response):
    """Clear the current session cookie."""
    clear_session_cookie(response)
    return {"success": True}


@router.get("/api/profile/{user_id}")
async def get_profile(user_id: str, request: Request):
    """Return a user's stored profile."""
    try:
        ensure_user_access(user_id, get_authenticated_user(request))
        return {"user_id": user_id, "profile": load_profile(user_id)}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile load failed")
        raise HTTPException(status_code=500, detail=f"Profile load failed: {exc}") from exc


@router.put("/api/profile/{user_id}")
async def update_profile(user_id: str, req: SaveProfileRequest, request: Request):
    """Persist a user's profile updates."""
    try:
        ensure_user_access(user_id, get_authenticated_user(request))
        save_profile(user_id, req.profile)
        return {"user_id": user_id, "profile": load_profile(user_id)}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile save failed")
        raise HTTPException(status_code=500, detail=f"Profile save failed: {exc}") from exc


@router.get("/api/reference-values/{category}")
async def reference_values(category: str):
    """Return reference values such as cities, countries, and airlines."""
    try:
        return {"category": category, "values": list_reference_values(category)}
    except Exception as exc:
        logger.exception("Reference values load failed")
        raise HTTPException(status_code=500, detail=f"Reference values load failed: {exc}") from exc
