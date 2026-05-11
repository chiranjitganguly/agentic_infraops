"""T054 — SSE router: GET /jobs/{job_id}/stream

Streams provisioning job status changes via asyncpg LISTEN/NOTIFY.
Uses sse_starlette EventSourceResponse.
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

router = APIRouter(tags=["jobs"])

_TERMINAL_STATUSES = frozenset({"completed", "succeeded", "failed", "rolled_back", "cancelled"})


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


async def job_status_stream(
    job_id: uuid.UUID,
    db_listener: _AsyncpgListener,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE events for a provisioning job until it reaches a terminal state.

    Filters LISTEN/NOTIFY payloads to only those matching job_id.
    Emits event:status for each matching update and event:done (empty data) on terminal.
    """
    async for payload in db_listener.listen("infraops_job_status"):
        data = json.loads(payload)
        if data.get("job_id") != str(job_id):
            continue
        status = data.get("status", "")
        yield {"event": "status", "data": json.dumps({"job_id": str(job_id), "status": status})}
        if status in _TERMINAL_STATUSES:
            yield {"event": "done", "data": ""}
            return


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
