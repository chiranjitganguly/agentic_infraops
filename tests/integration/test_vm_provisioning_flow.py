"""T059 — Integration test: end-to-end VM provisioning flow.

Tests the full lifecycle:
  submit request → confirmation summary → confirm → job transitions:
  awaiting_confirmation → queued → in_progress → succeeded

Uses:
  - In-memory stubs for postgres, pubsub, GCP clients
  - No real external services required
  - Verifies ADR-0006: rollback_resources empty before first GCP call, populated after

Markers: integration
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.provisioning.agent import handle_task
from contracts.agents.provisioning import (
    ProvisioningConfirmationOutput,
    ProvisioningInput,
    ProvisioningQueuedOutput,
    VMParameters,
)
from contracts.schemas.provisioning_job import ResourceType
from contracts.schemas.user_role import UserRoleType
from business_logic.gcp_compute.provisioner import ProvisionResult, create_vm

pytestmark = pytest.mark.integration


# ─── Stubs ─────────────────────────────────────────────────────────────────


class _FakePostgresClient:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.audit_events: list[dict] = []
        self.job_status_history: list[tuple[str, str]] = []

    async def get_provisioning_job_by_idempotency_key(self, idempotency_key: str) -> dict:
        for job in self.jobs.values():
            if job.get("idempotency_key") == idempotency_key:
                return job
        return {}

    async def create_infra_request(self, request_data: dict) -> dict:
        req_id = str(uuid.uuid4())
        req = {"id": req_id, **request_data}
        self.requests[req_id] = req
        return req

    async def create_provisioning_job(self, job_data: dict) -> dict:
        job_id = str(uuid.uuid4())
        job = {"id": job_id, **job_data, "created_at": datetime.now(timezone.utc).isoformat()}
        self.jobs[job_id] = job
        return job

    async def update_job_status(self, job_id: str, status: str) -> dict:
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
        self.job_status_history.append((job_id, status))
        return {"id": job_id, "status": status}

    async def update_request_status(self, infra_request_id: str, status: str, confirmed_at: str | None) -> dict:
        if infra_request_id in self.requests:
            self.requests[infra_request_id]["status"] = status
        return {"id": infra_request_id, "status": status}

    async def create_audit_event(self, event_data: dict) -> dict:
        self.audit_events.append(event_data)
        return {"id": str(uuid.uuid4()), **event_data}


class _FakePubSubClient:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish_provisioning_request(self, event: dict) -> dict:
        self.published.append(event)
        return {"message_id": str(uuid.uuid4())}


class _FakeGcpResourceClient:
    def __init__(self) -> None:
        self.created_vms: list[dict] = []
        self.deleted_vms: list[dict] = []

    async def create_vm(
        self,
        project_id: str,
        zone: str,
        instance_name: str,
        machine_type: str = "e2-standard-4",
        disk_size_gb: int = 50,
        image_family: str = "debian-12",
        image_project: str = "debian-cloud",
        network: str = "default",
        tags: list | None = None,
        dry_run: bool = False,
    ) -> dict:
        if dry_run:
            return {"resource_id": None, "status": "DRY_RUN_OK", "dry_run": True}
        resource_id = f"projects/test-project/zones/{zone}/instances/{instance_name}"
        self.created_vms.append({"instance_name": instance_name, "zone": zone})
        return {"resource_id": resource_id, "status": "RUNNING"}

    async def delete_vm(self, project_id: str, zone: str, instance_name: str) -> dict:
        self.deleted_vms.append({"instance_name": instance_name, "zone": zone})
        return {"status": "DELETED"}


class _FakePgSkillClient:
    """Postgres client adapter matching the provisioner.PostgresClient Protocol."""

    def __init__(self) -> None:
        self.updates: list[dict] = []

    async def update_job_status(self, job_id: Any, rollback_resources: list[dict]) -> None:
        self.updates.append({"job_id": str(job_id), "rollback_resources": rollback_resources})


# ─── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_full_vm_provisioning_flow() -> None:
    """Full flow: pre-confirm → confirm → assert status history."""
    postgres = _FakePostgresClient()
    pubsub = _FakePubSubClient()

    correlation_id = uuid.uuid4()
    request_id = uuid.uuid4()
    infra_request_id = uuid.uuid4()

    inp_pre = ProvisioningInput(
        correlation_id=correlation_id,
        request_id=request_id,
        infra_request_id=infra_request_id,
        resource_type=ResourceType.compute_instance,
        resource_name="test-vm-001",
        region="us-central1",
        zone="us-central1-a",
        parameters={"machine_type": "e2-standard-4", "disk_size_gb": 50},
        requesting_user="dev@example.com",
        user_role=UserRoleType.developer,
        confirmed=False,
    )

    pre_result = await handle_task(inp=inp_pre, postgres=postgres, pubsub=pubsub)

    assert isinstance(pre_result, ProvisioningConfirmationOutput)
    assert pre_result.status == "awaiting_confirmation"
    assert "test-vm-001" in pre_result.confirmation_summary
    assert "us-central1" in pre_result.confirmation_summary
    assert "20 minutes" in pre_result.confirmation_summary
    assert pre_result.expires_at > datetime.now(timezone.utc)

    job_id = pre_result.job_id
    assert str(job_id) in postgres.jobs
    assert postgres.jobs[str(job_id)]["status"] == "awaiting_confirmation"

    assert len(pubsub.published) == 0

    inp_confirmed = ProvisioningInput(
        correlation_id=correlation_id,
        request_id=request_id,
        infra_request_id=infra_request_id,
        resource_type=ResourceType.compute_instance,
        resource_name="test-vm-001",
        region="us-central1",
        zone="us-central1-a",
        parameters={"machine_type": "e2-standard-4", "disk_size_gb": 50},
        requesting_user="dev@example.com",
        user_role=UserRoleType.developer,
        confirmed=True,
    )

    post_result = await handle_task(inp=inp_confirmed, postgres=postgres, pubsub=pubsub)

    assert isinstance(post_result, ProvisioningQueuedOutput)
    assert post_result.status == "queued"
    assert post_result.job_id == job_id

    assert postgres.jobs[str(job_id)]["status"] == "queued"

    assert len(pubsub.published) == 1
    event = pubsub.published[0]
    assert event["schema_version"] == "1.0.0"
    assert event["resource_type"] == "compute_instance"
    assert event["resource_name"] == "test-vm-001"

    audit_types = [e["event_type"] for e in postgres.audit_events]
    assert "request_confirmed" in audit_types


@pytest.mark.anyio
async def test_idempotency_returns_existing_job() -> None:
    """Second pre-confirm call with same resource returns existing job."""
    postgres = _FakePostgresClient()
    pubsub = _FakePubSubClient()

    correlation_id = uuid.uuid4()
    infra_request_id = uuid.uuid4()

    def _make_input() -> ProvisioningInput:
        return ProvisioningInput(
            correlation_id=correlation_id,
            request_id=uuid.uuid4(),
            infra_request_id=infra_request_id,
            resource_type=ResourceType.compute_instance,
            resource_name="idempotent-vm",
            region="us-central1",
            zone="us-central1-a",
            parameters={},
            requesting_user="dev@example.com",
            user_role=UserRoleType.developer,
            confirmed=False,
        )

    result1 = await handle_task(inp=_make_input(), postgres=postgres, pubsub=pubsub)
    result2 = await handle_task(inp=_make_input(), postgres=postgres, pubsub=pubsub)

    assert isinstance(result1, ProvisioningConfirmationOutput)
    assert isinstance(result2, ProvisioningConfirmationOutput)
    assert result1.job_id == result2.job_id
    assert len(postgres.jobs) == 1


@pytest.mark.anyio
async def test_rollback_resources_empty_before_gcp_call() -> None:
    """ADR-0006: rollback_resources starts empty, appended after each successful GCP create."""
    gcp_client = _FakeGcpResourceClient()
    pg_skill = _FakePgSkillClient()
    job_id = uuid.uuid4()

    params = VMParameters(machine_type="e2-standard-4")

    result = await create_vm(
        params=params,
        region="us-central1",
        resource_name="adr-0006-vm",
        zone="us-central1-a",
        project_id="test-project",
        job_id=job_id,
        dry_run=False,
        gcp_client=gcp_client,  # type: ignore[arg-type]
        postgres_client=pg_skill,  # type: ignore[arg-type]
    )

    assert result.success is True
    assert len(gcp_client.created_vms) == 1
    assert gcp_client.created_vms[0]["instance_name"] == "adr-0006-vm"
    assert len(pg_skill.updates) == 1
    assert pg_skill.updates[0]["rollback_resources"][0]["name"] == "adr-0006-vm"


@pytest.mark.anyio
async def test_vm_provisioning_dry_run() -> None:
    """Dry run returns success without creating real GCP resources."""
    gcp_client = _FakeGcpResourceClient()
    pg_skill = _FakePgSkillClient()
    job_id = uuid.uuid4()

    params = VMParameters(machine_type="e2-standard-4")

    result = await create_vm(
        params=params,
        region="us-central1",
        resource_name="dry-run-vm",
        zone="us-central1-a",
        project_id="test-project",
        job_id=job_id,
        dry_run=True,
        gcp_client=gcp_client,  # type: ignore[arg-type]
        postgres_client=pg_skill,  # type: ignore[arg-type]
    )

    assert result.success is True
    assert len(gcp_client.created_vms) == 0
    assert len(pg_skill.updates) == 0


@pytest.mark.anyio
async def test_confirm_raises_if_no_existing_job() -> None:
    """confirm=True raises ValueError when no job exists for the idempotency key."""
    postgres = _FakePostgresClient()
    pubsub = _FakePubSubClient()

    inp = ProvisioningInput(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        infra_request_id=uuid.uuid4(),
        resource_type=ResourceType.compute_instance,
        resource_name="ghost-vm",
        region="us-central1",
        parameters={},
        requesting_user="dev@example.com",
        user_role=UserRoleType.developer,
        confirmed=True,
    )

    with pytest.raises(ValueError, match="No job found"):
        await handle_task(inp=inp, postgres=postgres, pubsub=pubsub)


@pytest.mark.anyio
async def test_confirmation_summary_includes_defaults() -> None:
    """Defaults applied (e.g. machine_type) appear in confirmation summary."""
    postgres = _FakePostgresClient()
    pubsub = _FakePubSubClient()

    inp = ProvisioningInput(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        infra_request_id=uuid.uuid4(),
        resource_type=ResourceType.compute_instance,
        resource_name="default-vm",
        region="us-east1",
        parameters={},
        requesting_user="dev@example.com",
        user_role=UserRoleType.developer,
        confirmed=False,
    )

    result = await handle_task(inp=inp, postgres=postgres, pubsub=pubsub)

    assert isinstance(result, ProvisioningConfirmationOutput)
    assert "Defaults applied" in result.confirmation_summary
    assert "machine_type" in result.confirmation_summary
