import json
import pytest
from uuid import UUID

from web.backend.routers.sse import job_status_stream


JOB_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
OTHER_JOB_ID = UUID("bbbbbbbb-0000-0000-0000-000000000002")


def notify(job_id: UUID, status: str) -> str:
    return json.dumps({"job_id": str(job_id), "status": status, "updated_at": "2026-05-10T00:00:00Z"})


class FakeListener:
    def __init__(self, payloads: list[str]):
        self._payloads = payloads

    async def listen(self, channel: str):
        for payload in self._payloads:
            yield payload


async def collect(job_id: UUID, payloads: list[str]) -> list[dict]:
    listener = FakeListener(payloads)
    return [event async for event in job_status_stream(job_id=job_id, db_listener=listener)]


# B1: matching job_id → status event yielded with correct shape
@pytest.mark.anyio
async def test_matching_notification_yields_status_event():
    events = await collect(JOB_ID, [notify(JOB_ID, "in_progress")])

    assert len(events) == 1
    assert events[0]["event"] == "status"
    data = json.loads(events[0]["data"])
    assert data["job_id"] == str(JOB_ID)
    assert data["status"] == "in_progress"


# B2: notification for a different job_id is silently skipped
@pytest.mark.anyio
async def test_non_matching_job_id_is_filtered():
    events = await collect(JOB_ID, [
        notify(OTHER_JOB_ID, "in_progress"),  # different job — should be skipped
        notify(JOB_ID, "in_progress"),        # our job — should appear
    ])

    assert len(events) == 1
    data = json.loads(events[0]["data"])
    assert data["job_id"] == str(JOB_ID)


# B3+B4: terminal status → status event + done event, stream stops (no events after done)
@pytest.mark.anyio
@pytest.mark.parametrize("terminal_status", ["succeeded", "failed", "cancelled"])
async def test_terminal_status_yields_done_and_stops_stream(terminal_status):
    events = await collect(JOB_ID, [
        notify(JOB_ID, "in_progress"),
        notify(JOB_ID, terminal_status),
        notify(JOB_ID, "in_progress"),  # must not appear — stream already closed
    ])

    assert len(events) == 3  # in_progress event, terminal event, done event
    assert events[0]["event"] == "status"
    assert json.loads(events[0]["data"])["status"] == "in_progress"

    assert events[1]["event"] == "status"
    assert json.loads(events[1]["data"])["status"] == terminal_status

    assert events[2]["event"] == "done"
    assert events[2]["data"] == ""
