import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from agents.provisioning.agent import handle_task, ProvisioningInput


CORRELATION_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
REQUEST_ID = UUID("bbbbbbbb-0000-0000-0000-000000000002")
INFRA_REQUEST_ID = UUID("cccccccc-0000-0000-0000-000000000003")
JOB_ID = UUID("dddddddd-0000-0000-0000-000000000004")


def make_input(confirmed=False):
    return ProvisioningInput(
        correlation_id=CORRELATION_ID,
        request_id=REQUEST_ID,
        infra_request_id=INFRA_REQUEST_ID,
        resource_type="compute_instance",
        resource_name="my-vm",
        region="us-central1",
        zone="us-central1-a",
        parameters={"machine_type": "e2-standard-4"},
        requesting_user="dev@example.com",
        user_role="developer",
        confirmed=confirmed,
    )


def expected_idempotency_key():
    raw = "compute_instance:my-vm:us-central1"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_postgres(existing_job=None):
    client = MagicMock()
    client.get_provisioning_job_by_idempotency_key = AsyncMock(return_value=existing_job)
    client.create_provisioning_job = AsyncMock(return_value={
        "id": str(JOB_ID),
        "status": "awaiting_confirmation",
        "idempotency_key": expected_idempotency_key(),
    })
    client.update_job_status = AsyncMock(return_value={"id": str(JOB_ID), "status": "queued"})
    client.update_request_status = AsyncMock(return_value={"id": str(INFRA_REQUEST_ID), "status": "confirmed"})
    client.create_audit_event = AsyncMock(return_value={"id": "audit-1"})
    return client


def make_pubsub():
    client = MagicMock()
    client.publish_provisioning_request = AsyncMock()
    return client


# B1: confirmed=False, no existing job → new job created, idempotency key correct, expires_at ~20 min
@pytest.mark.anyio
async def test_pre_confirm_creates_job_with_correct_idempotency_key_and_expiry():
    pg = make_postgres(existing_job=None)
    ps = make_pubsub()
    before = datetime.now(timezone.utc)

    result = await handle_task(inp=make_input(confirmed=False), postgres=pg, pubsub=ps)

    # idempotency key checked with SHA-256(resource_type:name:region)
    pg.get_provisioning_job_by_idempotency_key.assert_called_once_with(
        idempotency_key=expected_idempotency_key()
    )

    # job created with awaiting_confirmation
    pg.create_provisioning_job.assert_called_once()
    create_call = pg.create_provisioning_job.call_args.args[0]
    assert create_call["status"] == "awaiting_confirmation"
    assert create_call["idempotency_key"] == expected_idempotency_key()

    # output shape
    assert result.status == "awaiting_confirmation"
    assert result.job_id == JOB_ID
    assert result.existing_job is None
    assert result.idempotency_key == expected_idempotency_key()

    # expires_at is approximately 20 minutes from now
    expires_at = result.expires_at
    assert expires_at > before + timedelta(minutes=19)
    assert expires_at < before + timedelta(minutes=21)

    # pubsub untouched on pre-confirmation
    ps.publish_provisioning_request.assert_not_called()


# B2: idempotency conflict → existing job returned, no new job created
@pytest.mark.anyio
async def test_pre_confirm_idempotency_conflict_returns_existing_job():
    existing_job = {
        "id": str(JOB_ID),
        "status": "awaiting_confirmation",
        "idempotency_key": expected_idempotency_key(),
        "confirmation_summary": "Create compute_instance 'my-vm' in us-central1.",
    }
    pg = make_postgres(existing_job=existing_job)
    ps = make_pubsub()

    result = await handle_task(inp=make_input(confirmed=False), postgres=pg, pubsub=ps)

    assert result.job_id == JOB_ID
    assert result.existing_job == existing_job
    assert result.status == "awaiting_confirmation"
    pg.create_provisioning_job.assert_not_called()
    ps.publish_provisioning_request.assert_not_called()


# B3: confirmed=True → request confirmed, job queued, PubSub published, audit emitted
@pytest.mark.anyio
async def test_post_confirm_transitions_job_to_queued_and_publishes():
    # postgres knows the job by idempotency key (it was created in the pre-confirm step)
    existing_job = {"id": str(JOB_ID), "status": "awaiting_confirmation"}
    pg = make_postgres(existing_job=existing_job)
    ps = make_pubsub()

    result = await handle_task(inp=make_input(confirmed=True), postgres=pg, pubsub=ps)

    # InfraRequest moved to confirmed
    pg.update_request_status.assert_called_once()
    req_call = pg.update_request_status.call_args.kwargs
    assert req_call["infra_request_id"] == str(INFRA_REQUEST_ID)
    assert req_call["status"] == "confirmed"
    assert req_call["confirmed_at"] is not None

    # ProvisioningJob moved to queued
    pg.update_job_status.assert_called_once()
    job_call = pg.update_job_status.call_args.kwargs
    assert job_call["job_id"] == str(JOB_ID)
    assert job_call["status"] == "queued"

    # PubSub event published
    ps.publish_provisioning_request.assert_called_once()
    pub_call = ps.publish_provisioning_request.call_args.kwargs["event"]
    assert pub_call["job_id"] == str(JOB_ID)
    assert pub_call["resource_type"] == "compute_instance"

    # audit event emitted
    pg.create_audit_event.assert_called_once()

    # output carries queued status (not the retired "pending")
    assert result.status == "queued"
    assert result.job_id == JOB_ID
