"""T042 — GCP Compute provisioner skill.

create_vm(params, region, resource_name, zone, project_id, job_id, dry_run,
          gcp_client, postgres_client) → ProvisionResult

On dry_run=True: validates parameters, returns success without any GCP call.
On success: appends to rollback_resources via postgres_client.update_job_status.
Wrapped with @gcp_circuit_breaker at the GCP-call boundary (inside this skill).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from agentic_infraops.contracts.agents.provisioning import VMParameters
from agentic_infraops.contracts.shared.circuit_breaker import CircuitOpenError
from agentic_infraops.contracts.shared.logging import get_logger

logger = get_logger("gcp-provisioner")


class GcpResourceClient(Protocol):
    async def create_vm(
        self,
        project_id: str,
        zone: str,
        instance_name: str,
        machine_type: str,
        disk_size_gb: int,
        image_family: str,
        image_project: str,
        network: str,
        tags: list[str],
        dry_run: bool,
    ) -> dict: ...


class PostgresClient(Protocol):
    async def update_job_status(
        self,
        job_id: UUID,
        rollback_resources: list[dict],
    ) -> None: ...


@dataclass
class ProvisionResult:
    success: bool
    gcp_resource_id: str | None = None
    error_message: str | None = None


async def create_vm(
    params: VMParameters,
    region: str,
    resource_name: str,
    zone: str,
    project_id: str,
    job_id: UUID,
    dry_run: bool,
    gcp_client: GcpResourceClient,
    postgres_client: PostgresClient,
) -> ProvisionResult:
    """Create a GCP Compute Engine VM instance.

    On dry_run=True, validates parameters without any GCP API call and without
    updating rollback_resources (CONTEXT.md: never pre-populate from dry-run).

    On success, immediately appends to rollback_resources before returning
    so the DAG can roll back even if a subsequent step fails.

    Args:
        params: VMParameters (machine_type, disk_size_gb, image_family, etc.).
        region: GCP region (e.g. us-central1).
        resource_name: Instance name.
        zone: GCP zone (e.g. us-central1-a).
        project_id: GCP project ID.
        job_id: ProvisioningJob UUID for rollback tracking.
        dry_run: If True, validate only — do not call GCP.
        gcp_client: MCP client for GCP resource operations.
        postgres_client: MCP client for PostgreSQL state updates.
    """
    if dry_run:
        logger.info("create_vm_dry_run", resource_name=resource_name, zone=zone)
        return ProvisionResult(success=True)

    try:
        response = await gcp_client.create_vm(
            project_id=project_id,
            zone=zone,
            instance_name=resource_name,
            machine_type=params.machine_type,
            disk_size_gb=params.disk_size_gb,
            image_family=params.image_family,
            image_project=params.image_project,
            network=params.network,
            tags=params.tags,
            dry_run=False,
        )
    except CircuitOpenError as exc:
        logger.warning("create_vm_circuit_open", resource_name=resource_name, error=str(exc))
        return ProvisionResult(success=False, error_message=f"GCP API circuit breaker open: {exc}")
    except Exception as exc:
        logger.error("create_vm_failed", resource_name=resource_name, error=str(exc))
        return ProvisionResult(success=False, error_message=str(exc))

    await postgres_client.update_job_status(
        job_id=job_id,
        rollback_resources=[
            {
                "type": "compute_instance",
                "name": resource_name,
                "region": region,
                "zone": zone,
                "gcp_resource_id": response.get("resource_id"),
            }
        ],
    )

    logger.info("create_vm_succeeded", resource_name=resource_name, gcp_resource_id=response.get("resource_id"))
    return ProvisionResult(success=True, gcp_resource_id=response["resource_id"])
