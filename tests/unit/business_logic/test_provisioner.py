import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from contracts.agents.provisioning import VMParameters
from business_logic.gcp_compute.provisioner import create_vm


JOB_ID = UUID("00000000-0000-0000-0000-000000000001")
PARAMS = VMParameters(machine_type="e2-standard-4")


def make_gcp_client(resource_id="projects/p/zones/z/instances/vm-1"):
    client = MagicMock()
    client.create_vm = AsyncMock(return_value={"resource_id": resource_id, "status": "RUNNING"})
    return client


def make_postgres_client():
    client = MagicMock()
    client.update_job_status = AsyncMock()
    return client


# B1: dry_run=True → success, no GCP call, no postgres call
@pytest.mark.anyio
async def test_dry_run_returns_success_without_side_effects():
    gcp = make_gcp_client()
    pg = make_postgres_client()

    result = await create_vm(
        params=PARAMS,
        region="us-central1",
        resource_name="my-vm",
        zone="us-central1-a",
        project_id="my-project",
        job_id=JOB_ID,
        dry_run=True,
        gcp_client=gcp,
        postgres_client=pg,
    )

    assert result.success is True
    gcp.create_vm.assert_not_called()
    pg.update_job_status.assert_not_called()


# B2: GCP succeeds → resource_id returned, rollback entry appended in postgres
@pytest.mark.anyio
async def test_successful_provision_returns_resource_id_and_updates_rollback():
    gcp = make_gcp_client(resource_id="projects/my-project/zones/us-central1-a/instances/my-vm")
    pg = make_postgres_client()

    result = await create_vm(
        params=PARAMS,
        region="us-central1",
        resource_name="my-vm",
        zone="us-central1-a",
        project_id="my-project",
        job_id=JOB_ID,
        dry_run=False,
        gcp_client=gcp,
        postgres_client=pg,
    )

    assert result.success is True
    assert result.gcp_resource_id == "projects/my-project/zones/us-central1-a/instances/my-vm"

    pg.update_job_status.assert_called_once()
    call_kwargs = pg.update_job_status.call_args.kwargs
    assert call_kwargs["job_id"] == JOB_ID
    rollback = call_kwargs["rollback_resources"]
    assert len(rollback) == 1
    assert rollback[0]["type"] == "compute_instance"
    assert rollback[0]["name"] == "my-vm"
    assert rollback[0]["region"] == "us-central1"


# B3: GCP raises → failure with error_message, postgres never called
@pytest.mark.anyio
async def test_gcp_failure_returns_failure_without_updating_rollback():
    gcp = make_gcp_client()
    gcp.create_vm = AsyncMock(side_effect=RuntimeError("GCP quota exceeded"))
    pg = make_postgres_client()

    result = await create_vm(
        params=PARAMS,
        region="us-central1",
        resource_name="my-vm",
        zone="us-central1-a",
        project_id="my-project",
        job_id=JOB_ID,
        dry_run=False,
        gcp_client=gcp,
        postgres_client=pg,
    )

    assert result.success is False
    assert "GCP quota exceeded" in result.error_message
    pg.update_job_status.assert_not_called()
