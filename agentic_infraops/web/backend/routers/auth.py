"""T055 — /auth router.

GET  /auth/me          — current user info + daily count
POST /auth/rotate-key  — generate new API key, invalidate old one, return plaintext once
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["auth"])


@router.get("/auth/me")
async def get_me(request: Request) -> JSONResponse:
    user_id: str = getattr(request.state, "user_id", "")
    user_role_dict: dict = getattr(request.state, "user_role", {})

    from agentic_infraops.mcp_servers.postgres import server as pg

    usage = await pg.get_daily_usage_count(requesting_user=user_id)
    daily_count = usage.get("count", 0)
    daily_limit = usage.get("limit", 10)

    api_key_expires_at = user_role_dict.get("api_key_expires_at")

    return JSONResponse(
        status_code=200,
        content={
            "user_id": user_id,
            "role": user_role_dict.get("role", "developer"),
            "api_key_expires_at": api_key_expires_at,
            "daily_provisioning_count": daily_count,
            "daily_provisioning_limit": daily_limit,
        },
    )


@router.post("/auth/rotate-key")
async def rotate_key(request: Request) -> JSONResponse:
    import bcrypt

    user_id: str = getattr(request.state, "user_id", "")

    new_key = secrets.token_urlsafe(32)
    hashed = bcrypt.hashpw(new_key.encode(), bcrypt.gensalt()).decode()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()

    from agentic_infraops.mcp_servers.postgres import server as pg

    await pg.rotate_api_key(
        user_id=user_id,
        new_key_hash=hashed,
        expires_at=expires_at,
    )

    return JSONResponse(
        status_code=200,
        content={
            "api_key": new_key,
            "expires_at": expires_at,
        },
    )
