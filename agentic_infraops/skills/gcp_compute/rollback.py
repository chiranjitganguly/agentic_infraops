"""T043 — GCP Compute rollback skill.

rollback_vm(rollback_resources, gcp_client) → RollbackResult

Iterates rollback_resources, calls gcp-resource-mcp delete_vm for each.
404 responses are ignored — the resource may have never been created or was
already deleted by a previous rollback attempt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agentic_infraops.contracts.schemas.provisioning_job import RollbackResource
from agentic_infraops.contracts.shared.logging import get_logger

logger = get_logger("gcp-compute")


class GcpResourceClient(Protocol):
    async def delete_vm(
        self,
        project_id: str,
        zone: str,
        instance_name: str,
    ) -> dict: ...


@dataclass
class RollbackAttempt:
    resource_name: str
    zone: str
    status: str
    error: str | None = None


@dataclass
class RollbackResult:
    success: bool
    attempts: list[RollbackAttempt] = field(default_factory=list)

    @property
    def all_deleted(self) -> bool:
        return all(a.status in {"DELETED", "NOT_FOUND"} for a in self.attempts)


async def rollback_vm(
    rollback_resources: list[RollbackResource],
    project_id: str,
    gcp_client: GcpResourceClient,
) -> RollbackResult:
    """Delete all VMs listed in rollback_resources.

    Called by the Airflow DAG rollback_group when provisioning fails after one
    or more GCP create calls succeeded. 404 responses are ignored (idempotent).

    Args:
        rollback_resources: List of resources appended after each successful GCP create.
        project_id: GCP project ID.
        gcp_client: MCP client for GCP resource operations.

    Returns:
        RollbackResult indicating overall success and per-resource attempt status.
    """
    if not rollback_resources:
        logger.info("rollback_vm_no_resources")
        return RollbackResult(success=True)

    attempts: list[RollbackAttempt] = []

    for resource in rollback_resources:
        if resource.resource_type != "compute_instance":
            continue

        zone = resource.zone or f"{resource.region}-a"
        logger.info("rollback_vm_deleting", resource_name=resource.name, zone=zone)

        try:
            result = await gcp_client.delete_vm(
                project_id=project_id,
                zone=zone,
                instance_name=resource.name,
            )
            status = result.get("status", "DELETED")
            attempts.append(RollbackAttempt(resource_name=resource.name, zone=zone, status=status))
            logger.info("rollback_vm_deleted", resource_name=resource.name, status=status)
        except Exception as exc:
            logger.error("rollback_vm_error", resource_name=resource.name, error=str(exc))
            attempts.append(
                RollbackAttempt(resource_name=resource.name, zone=zone, status="ERROR", error=str(exc))
            )

    overall_success = all(a.status in {"DELETED", "NOT_FOUND"} for a in attempts)
    return RollbackResult(success=overall_success, attempts=attempts)
