"""T088 — GCP Network rollback skill.

rollback_vpc(rollback_resources, project_id, gcp_client) → RollbackResult

Iterates rollback_resources in REVERSE order (last created first) per ADR-0006.
Subnet deletion is best-effort; VPC network deletion is the critical step.
404 / NOT_FOUND responses are ignored — resource may never have been created.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from contracts.schemas.provisioning_job import RollbackResource
from contracts.shared.logging import get_logger

logger = get_logger("gcp-network-rollback")


class GcpResourceClient(Protocol):
    async def delete_vpc_network(
        self,
        project_id: str,
        network_name: str,
    ) -> dict: ...


@dataclass
class RollbackAttempt:
    resource_name: str
    resource_type: str
    status: str
    error: str | None = None


@dataclass
class RollbackResult:
    success: bool
    attempts: int = 0
    errors: list[str] = field(default_factory=list)


async def rollback_vpc(
    rollback_resources: list[RollbackResource],
    project_id: str,
    gcp_client: GcpResourceClient,
) -> RollbackResult:
    """Delete VPC resources created during a failed provisioning run.

    Processes rollback_resources in reverse order so subnets are attempted
    before VPC networks (matching creation order reversal per ADR-0006).
    Subnet deletion is logged but not enforced via API — GCP auto-removes subnets
    when the parent network is deleted. 404 responses are silently ignored.

    Args:
        rollback_resources: List of resources appended during provisioning.
        project_id: GCP project ID.
        gcp_client: Injectable GCP resource client.
    """
    if not rollback_resources:
        logger.info("rollback_vpc_no_resources")
        return RollbackResult(success=True, attempts=0)

    attempts = 0
    errors: list[str] = []

    for resource in reversed(rollback_resources):
        if resource.resource_type == "vpc_subnetwork":
            # GCP removes subnets when parent network is deleted — log and skip
            logger.info(
                "rollback_vpc_skipping_subnet",
                subnet_name=resource.name,
                note="subnet deleted automatically with parent VPC",
            )
            continue

        if resource.resource_type != "vpc_network":
            continue

        attempts += 1
        logger.info("rollback_vpc_deleting", resource_name=resource.name)

        try:
            result = await gcp_client.delete_vpc_network(
                project_id=project_id,
                network_name=resource.name,
            )
            status = result.get("status", "DELETED")
            if "NOT_FOUND" in status or "not found" in str(result).lower():
                logger.info("rollback_vpc_not_found", resource_name=resource.name)
            else:
                logger.info("rollback_vpc_deleted", resource_name=resource.name, status=status)
        except Exception as exc:
            err = str(exc)
            if "not found" in err.lower() or "404" in err:
                logger.info("rollback_vpc_not_found", resource_name=resource.name)
            else:
                logger.error("rollback_vpc_error", resource_name=resource.name, error=err)
                errors.append(f"{resource.name}: {err}")

    return RollbackResult(success=not errors, attempts=attempts, errors=errors)
