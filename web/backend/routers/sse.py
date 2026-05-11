"""T054 — SSE router: GET /jobs/{job_id}/stream

Wraps the job_status_stream() business logic from web/backend/routers/sse.py.
Uses asyncpg LISTEN/NOTIFY on infraops_job_status channel.
Sends event: done and closes on terminal status.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncIterator

import asyncpg
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from web.backend.routers.sse import job_status_stream

router = APIRouter(tags=["jobs"])


class _AsyncpgListener:
    """DbListener adapter backed by asyncpg LISTEN/NOTIFY."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def listen(self, channel: str) -> AsyncIterator[str]:
        conn: asyncpg.Connection = await asyncpg.connect(self._dsn)
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _on_notify(connection: asyncpg.Connection, pid: int, chan: str, payload: str) -> None:
            queue.put_nowait(payload)

        try:
            await conn.add_listener(channel, _on_notify)
            while True:
                payload = await queue.get()
                yield payload
        finally:
            await conn.remove_listener(channel, _on_notify)
            await conn.close()


@router.get("/jobs/{job_id}/stream")
async def stream_job_status(job_id: uuid.UUID, request: Request) -> EventSourceResponse:
    import os

    dsn = os.environ.get("DATABASE_URL", "")
    listener = _AsyncpgListener(dsn)

    async def event_generator() -> AsyncIterator[dict]:
        async for event in job_status_stream(job_id=job_id, db_listener=listener):
            if await request.is_disconnected():
                break
            yield event

    return EventSourceResponse(event_generator())
