"""T038 — gcp-resource-mcp: MCP server wrapping GCP Compute Engine API (VM subset).

VM tools: create_vm, delete_vm, get_vm_status.
All tools wrapped with @gcp_circuit_breaker (5 failures → open, 60s reset).
"""
from __future__ import annotations

import os
from typing import Any

from googleapiclient import discovery
from googleapiclient.errors import HttpError
from mcp.server.fastmcp import FastMCP

from contracts.shared.circuit_breaker import CircuitOpenError, gcp_circuit_breaker
from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="gcp-resource-mcp")
logger = get_logger("gcp-resource-mcp")

mcp = FastMCP("gcp-resource-mcp")

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")

_compute_client: Any = None


def _get_compute() -> Any:
    global _compute_client
    if _compute_client is None:
        _compute_client = discovery.build("compute", "v1")
    return _compute_client


@mcp.tool()
@gcp_circuit_breaker(tool="get_vm_status", resource_type="compute_instance")
def get_vm_status(project_id: str, zone: str, instance_name: str) -> dict[str, Any]:
    """Get the status of a Compute Engine VM instance.

    Args:
        project_id: GCP project ID.
        zone: Zone where the instance resides (e.g. us-central1-a).
        instance_name: Name of the Compute Engine instance.
    """
    compute = _get_compute()
    try:
        result = (
            compute.instances()
            .get(project=project_id, zone=zone, instance=instance_name)
            .execute()
        )
        return {
            "resource_type": "compute_instance",
            "name": result["name"],
            "gcp_status": result["status"],
            "zone": zone,
            "machine_type": result["machineType"].split("/")[-1],
            "metadata": {
                "network_interfaces": [
                    {
                        "network": ni.get("network", "").split("/")[-1],
                        "access_configs": ni.get("accessConfigs", []),
                    }
                    for ni in result.get("networkInterfaces", [])
                ],
                "creation_timestamp": result.get("creationTimestamp"),
            },
        }
    except HttpError as exc:
        if exc.resp.status == 404:
            return {"gcp_status": "NOT_FOUND", "name": instance_name}
        raise


@mcp.tool()
@gcp_circuit_breaker(tool="create_vm", resource_type="compute_instance")
def create_vm(
    project_id: str,
    zone: str,
    instance_name: str,
    machine_type: str = "e2-standard-4",
    disk_size_gb: int = 50,
    image_family: str = "debian-12",
    image_project: str = "debian-cloud",
    network: str = "default",
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a Compute Engine VM instance.

    When dry_run=True, validates parameters without calling the GCP API.

    Args:
        project_id: GCP project ID.
        zone: Zone to create the instance in (e.g. us-central1-a).
        instance_name: Name for the new instance.
        machine_type: Machine type (e.g. e2-standard-4).
        disk_size_gb: Boot disk size in GB (10–2000).
        image_family: Source image family (e.g. debian-12).
        image_project: Project hosting the image (e.g. debian-cloud).
        network: VPC network name (default: 'default').
        tags: Network tags to apply.
        dry_run: If True, validate only — do not call GCP.
    """
    if not (10 <= disk_size_gb <= 2000):
        raise ValueError(f"disk_size_gb must be 10–2000, got {disk_size_gb}")
    if not instance_name:
        raise ValueError("instance_name must not be empty")

    if dry_run:
        logger.info("create_vm_dry_run", instance_name=instance_name, zone=zone)
        return {"resource_id": None, "status": "DRY_RUN_OK", "dry_run": True}

    compute = _get_compute()
    machine_type_url = f"zones/{zone}/machineTypes/{machine_type}"
    source_image = f"projects/{image_project}/global/images/family/{image_family}"
    network_url = f"global/networks/{network}"

    instance_body = {
        "name": instance_name,
        "machineType": machine_type_url,
        "disks": [
            {
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": source_image,
                    "diskSizeGb": str(disk_size_gb),
                },
            }
        ],
        "networkInterfaces": [{"network": network_url, "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}]}],
        "tags": {"items": tags or []},
    }

    operation = (
        compute.instances()
        .insert(project=project_id, zone=zone, body=instance_body)
        .execute()
    )
    _wait_for_zone_operation(compute, project_id, zone, operation["name"])

    instance = compute.instances().get(project=project_id, zone=zone, instance=instance_name).execute()
    resource_id = str(instance.get("id", ""))
    logger.info("create_vm_succeeded", instance_name=instance_name, resource_id=resource_id)
    return {"resource_id": resource_id, "status": "RUNNING"}


@mcp.tool()
@gcp_circuit_breaker(tool="delete_vm", resource_type="compute_instance")
def delete_vm(project_id: str, zone: str, instance_name: str) -> dict[str, Any]:
    """Delete a Compute Engine VM instance (rollback operation).

    Returns success even if the instance does not exist (404 is ignored).

    Args:
        project_id: GCP project ID.
        zone: Zone where the instance resides.
        instance_name: Name of the instance to delete.
    """
    compute = _get_compute()
    try:
        operation = (
            compute.instances()
            .delete(project=project_id, zone=zone, instance=instance_name)
            .execute()
        )
        _wait_for_zone_operation(compute, project_id, zone, operation["name"])
        logger.info("delete_vm_succeeded", instance_name=instance_name)
        return {"status": "DELETED"}
    except HttpError as exc:
        if exc.resp.status == 404:
            logger.info("delete_vm_not_found_ignored", instance_name=instance_name)
            return {"status": "NOT_FOUND"}
        raise


def _wait_for_zone_operation(compute: Any, project_id: str, zone: str, operation_name: str) -> None:
    import time
    while True:
        result = compute.zoneOperations().get(project=project_id, zone=zone, operation=operation_name).execute()
        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(f"GCP operation failed: {result['error']}")
            return
        time.sleep(2)


if __name__ == "__main__":
    mcp.run()
