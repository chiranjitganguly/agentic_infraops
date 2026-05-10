from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from contracts.agents.provisioning import VMParameters


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
    if dry_run:
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
    except Exception as exc:
        return ProvisionResult(success=False, error_message=str(exc))

    await postgres_client.update_job_status(
        job_id=job_id,
        rollback_resources=[{"type": "compute_instance", "name": resource_name, "region": region}],
    )

    return ProvisionResult(success=True, gcp_resource_id=response["resource_id"])
