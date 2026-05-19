"""T087 — GCP Network provisioner skill.

create_vpc(params, region, resource_name, project_id, job_id, dry_run,
           gcp_client, postgres_client) → ProvisionResult

Steps (ADR-0006: append rollback_resources after EACH successful GCP create):
  1. create_vpc_network — appends vpc_network rollback resource
  2. create_subnetwork  — appends vpc_subnetwork rollback resource (if subnet_name set)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from contracts.agents.provisioning import VPCParameters
from contracts.shared.circuit_breaker import CircuitOpenError
from contracts.shared.logging import get_logger

logger = get_logger("gcp-network-provisioner")


class GcpResourceClient(Protocol):
    async def create_vpc_network(
        self,
        project_id: str,
        network_name: str,
        dry_run: bool,
        auto_create_subnetworks: bool,
    ) -> dict: ...

    async def create_subnetwork(
        self,
        project_id: str,
        network_name: str,
        subnet_name: str,
        region: str,
        cidr_range: str,
        private_google_access: bool,
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


async def create_vpc(
    params: VPCParameters,
    region: str,
    resource_name: str,
    project_id: str,
    job_id: UUID,
    dry_run: bool,
    gcp_client: GcpResourceClient,
    postgres_client: PostgresClient,
) -> ProvisionResult:
    """Create a GCP VPC network and optional subnet.

    On dry_run=True, validates without any GCP API calls.
    On success, appends each created resource to rollback_resources immediately
    so the DAG can roll back if a subsequent step fails (ADR-0006).

    Args:
        params: VPCParameters (subnet_name, subnet_cidr, subnet_region, auto_create_subnetworks).
        region: GCP region for the subnet (fallback if params.subnet_region is unset).
        resource_name: VPC network name.
        project_id: GCP project ID.
        job_id: ProvisioningJob UUID for rollback tracking.
        dry_run: If True, validate only — do not call GCP.
        gcp_client: Injectable GCP resource client.
        postgres_client: Injectable PostgreSQL client for rollback tracking.
    """
    if dry_run:
        logger.info("create_vpc_dry_run", resource_name=resource_name, region=region)
        return ProvisionResult(success=True)

    # Step 1: Create VPC network
    try:
        await gcp_client.create_vpc_network(
            project_id=project_id,
            network_name=resource_name,
            dry_run=False,
            auto_create_subnetworks=params.auto_create_subnetworks,
        )
    except CircuitOpenError as exc:
        logger.warning("create_vpc_circuit_open", resource_name=resource_name, error=str(exc))
        return ProvisionResult(success=False, error_message=f"GCP API circuit breaker open: {exc}")
    except Exception as exc:
        logger.error("create_vpc_failed", resource_name=resource_name, error=str(exc))
        return ProvisionResult(success=False, error_message=str(exc))

    await postgres_client.update_job_status(
        job_id=job_id,
        rollback_resources=[
            {
                "type": "vpc_network",
                "name": resource_name,
                "region": region,
                "zone": None,
                "gcp_resource_id": f"projects/{project_id}/global/networks/{resource_name}",
            }
        ],
    )
    logger.info("create_vpc_network_succeeded", resource_name=resource_name)

    # Step 2: Create subnet if requested
    subnet_name = params.subnet_name
    if subnet_name:
        subnet_region = params.subnet_region or region
        try:
            await gcp_client.create_subnetwork(
                project_id=project_id,
                network_name=resource_name,
                subnet_name=subnet_name,
                region=subnet_region,
                cidr_range=params.subnet_cidr,
                private_google_access=True,
                dry_run=False,
            )
        except CircuitOpenError as exc:
            logger.warning("create_subnet_circuit_open", subnet_name=subnet_name, error=str(exc))
            return ProvisionResult(
                success=False,
                error_message=f"GCP API circuit breaker open (subnet): {exc}",
            )
        except Exception as exc:
            logger.error("create_subnet_failed", subnet_name=subnet_name, error=str(exc))
            return ProvisionResult(success=False, error_message=str(exc))

        await postgres_client.update_job_status(
            job_id=job_id,
            rollback_resources=[
                {
                    "type": "vpc_subnetwork",
                    "name": subnet_name,
                    "region": subnet_region,
                    "zone": subnet_region,
                    "gcp_resource_id": (
                        f"projects/{project_id}/regions/{subnet_region}/subnetworks/{subnet_name}"
                    ),
                }
            ],
        )
        logger.info("create_subnet_succeeded", subnet_name=subnet_name)

    gcp_resource_id = f"projects/{project_id}/global/networks/{resource_name}"
    return ProvisionResult(success=True, gcp_resource_id=gcp_resource_id)
