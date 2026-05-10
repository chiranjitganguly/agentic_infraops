"""T050 — FastAPI web backend entry point.

Mounts all routers under /api/v1.
Applies X-API-Key auth middleware to all routes except /health.
Manages asyncpg connection pool lifecycle.
"""
from __future__ import annotations

import os

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentic_infraops.contracts.shared.logging import configure_logging, get_logger
from agentic_infraops.web.backend.middleware.auth import AuthMiddleware
from agentic_infraops.web.backend.routers import auth, jobs, requests, sse

configure_logging(service_name="infraops-web")
logger = get_logger("infraops-web")

app = FastAPI(title="infraops-web", version="1.0.0")

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(requests.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(sse.router, prefix="/api/v1")


@app.on_event("startup")
async def startup() -> None:
    from agentic_infraops.mcp_servers.postgres import server as pg

    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
    )
    pg._pool = pool  # type: ignore[attr-defined]
    logger.info("db_pool_started")


@app.on_event("shutdown")
async def shutdown() -> None:
    from agentic_infraops.mcp_servers.postgres import server as pg

    if pg._pool is not None:  # type: ignore[attr-defined]
        await pg._pool.close()  # type: ignore[attr-defined]
        logger.info("db_pool_closed")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
