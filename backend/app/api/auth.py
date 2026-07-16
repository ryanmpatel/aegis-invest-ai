"""Authentication endpoints (single-user MVP)."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import auth_rate_limit, current_user
from app.config import Settings, get_settings
from app.utils.security import create_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
async def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict:
    stored_hash = settings.auth_password_hash.get_secret_value()
    if not stored_hash:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_PASSWORD_HASH is not configured. Generate one with "
            "`python -c \"from app.utils.security import hash_password; "
            "print(hash_password('yourpassword'))\"` and set it in .env.",
        )
    username_ok = hmac.compare_digest(body.username, settings.auth_username)
    password_ok = verify_password(body.password, stored_hash)
    if not (username_ok and password_ok):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")

    token, csrf_token = create_session_token(
        body.username,
        settings.app_secret_key.get_secret_value(),
        settings.session_ttl_minutes,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    return {"username": body.username, "csrf_token": csrf_token}


@router.post("/logout")
async def logout(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
async def me(username: str = Depends(current_user)) -> dict:
    return {"username": username}
