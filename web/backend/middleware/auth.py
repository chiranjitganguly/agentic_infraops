"""T051 — X-API-Key auth middleware with brute-force protection.

Validates X-API-Key header on every request except /health.
Attaches user_id, user_role to request.state on success.
5 failed attempts per IP per minute → 429.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

_EXEMPT_PATHS = {"/health", "/"}
_MAX_FAILURES = 5
_WINDOW_SECONDS = 60

_failure_tracker: dict[str, list[float]] = defaultdict(list)


def _check_brute_force(ip: str) -> bool:
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    attempts = [t for t in _failure_tracker[ip] if t >= window_start]
    _failure_tracker[ip] = attempts
    return len(attempts) >= _MAX_FAILURES


def _record_failure(ip: str) -> None:
    _failure_tracker[ip].append(time.monotonic())


def _error(status: int, error_code: str, message: str) -> JSONResponse:
    import uuid
    from datetime import datetime, timezone

    return JSONResponse(
        status_code=status,
        content={
            "error_code": error_code,
            "message": message,
            "details": {},
            "correlation_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if _check_brute_force(client_ip):
            return _error(429, "RATE_LIMIT_EXCEEDED", "Too many failed authentication attempts. Try again later.")

        api_key = request.headers.get("X-API-Key", "").strip()
        if not api_key:
            _record_failure(client_ip)
            return _error(401, "UNAUTHORIZED", "X-API-Key header is required.")

        try:
            from mcp_servers.postgres import server as pg

            result = await pg.verify_api_key(user_id="", api_key_plaintext=api_key)
        except Exception:
            return _error(500, "INTERNAL_ERROR", "Authentication service unavailable.")

        if not result.get("valid"):
            _record_failure(client_ip)
            return _error(401, "UNAUTHORIZED", "Invalid or expired API key.")

        request.state.user_id = result.get("user_id", "")
        request.state.user_role = result.get("user_role", {})
        return await call_next(request)
