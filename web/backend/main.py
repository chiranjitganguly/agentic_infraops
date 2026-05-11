"""T050 — FastAPI web backend entry point.

Mounts all routers under /api/v1.
Applies X-API-Key auth middleware to all routes except /health.
Manages asyncpg connection pool lifecycle.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contracts.shared.logging import configure_logging, get_logger
from web.backend.middleware.auth import AuthMiddleware
from web.backend.routers import auth, jobs, requests, sse

configure_logging(service_name="infraops-web")
logger = get_logger("infraops-web")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    from mcp_servers.postgres import server as pg

    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
    )
    pg._pool = pool  # type: ignore[attr-defined]
    logger.info("db_pool_started")

    yield

    if pg._pool is not None:  # type: ignore[attr-defined]
        await pg._pool.close()  # type: ignore[attr-defined]
        logger.info("db_pool_closed")


app = FastAPI(title="infraops-web", version="1.0.0", lifespan=lifespan)

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
