import json
from typing import AsyncIterator, Protocol
from uuid import UUID


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class DbListener(Protocol):
    async def listen(self, channel: str) -> AsyncIterator[str]: ...


async def job_status_stream(
    job_id: UUID,
    db_listener: DbListener,
) -> AsyncIterator[dict]:
    async for raw in db_listener.listen("infraops_job_status"):
        payload = json.loads(raw)
        if payload["job_id"] != str(job_id):
            continue

        yield {"event": "status", "data": json.dumps(payload)}

        if payload["status"] in TERMINAL_STATUSES:
            yield {"event": "done", "data": ""}
            return
