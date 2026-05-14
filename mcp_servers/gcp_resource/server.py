"""T038/T069 — gcp-resource-mcp: MCP server wrapping GCP Compute Engine, Cloud Storage, and VPC APIs.

VM tools:     create_vm, delete_vm, get_vm_status
Bucket tools: create_bucket, delete_bucket, get_bucket_status
VPC tools:    create_vpc_network, create_subnetwork, delete_vpc_network, get_vpc_status
List tools:   list_project_resources

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
_storage_client: Any = None


def _get_compute() -> Any:
    global _compute_client
    if _compute_client is None:
        _compute_client = discovery.build("compute", "v1")
    return _compute_client


def _get_storage() -> Any:
    global _storage_client
    if _storage_client is None:
        from google.cloud import storage
        _storage_client = storage.Client()
    return _storage_client


# ─── VM tools ────────────────────────────────────────────────────────────────

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
        nis = result.get("networkInterfaces", [{}])
        ni = nis[0] if nis else {}
        access_configs = ni.get("accessConfigs", [{}])
        external_ip = access_configs[0].get("natIP") if access_configs else None

        disks = result.get("disks", [{}])
        boot_disk = next((d for d in disks if d.get("boot")), {})
        disk_size_gb = int(boot_disk.get("diskSizeGb", 50))

        return {
            "resource_type": "compute_instance",
            "resource_name": result["name"],
            "gcp_status": result["status"],
            "zone": zone,
            "metadata": {
                "machine_type": result["machineType"].split("/")[-1],
                "zone": zone,
                "network": ni.get("network", ""),
                "subnetwork": ni.get("subnetwork"),
                "internal_ip": ni.get("networkIP"),
                "external_ip": external_ip,
                "disk_size_gb": disk_size_gb,
                "creation_timestamp": result.get("creationTimestamp"),
                "labels": result.get("labels", {}),
            },
        }
    except HttpError as exc:
        if exc.resp.status == 404:
            return {"gcp_status": "NOT_FOUND", "resource_name": instance_name}
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
        "networkInterfaces": [{"network": network_url}],
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


# ─── Bucket tools ─────────────────────────────────────────────────────────────

@mcp.tool()
@gcp_circuit_breaker(tool="get_bucket_status", resource_type="storage_bucket")
def get_bucket_status(project_id: str, bucket_name: str) -> dict[str, Any]:
    """Get the status of a Cloud Storage bucket.

    Args:
        project_id: GCP project ID.
        bucket_name: Name of the bucket.
    """
    storage = _get_storage()
    try:
        bucket = storage.get_bucket(bucket_name)
        iam_config = bucket.iam_configuration
        return {
            "resource_type": "storage_bucket",
            "resource_name": bucket.name,
            "gcp_status": "ACTIVE",
            "region": bucket.location.lower() if bucket.location else None,
            "metadata": {
                "storage_class": bucket.storage_class or "STANDARD",
                "location": bucket.location or "",
                "location_type": bucket.location_type or "region",
                "versioning_enabled": bucket.versioning_enabled,
                "uniform_bucket_level_access": iam_config.uniform_bucket_level_access_enabled,
                "public_access_prevention": iam_config.public_access_prevention or "enforced",
                "creation_time": bucket.time_created.isoformat() if bucket.time_created else None,
                "labels": bucket.labels or {},
            },
        }
    except Exception as exc:
        if "404" in str(exc) or "does not exist" in str(exc).lower():
            return {"gcp_status": "NOT_FOUND", "resource_name": bucket_name}
        raise


@mcp.tool()
@gcp_circuit_breaker(tool="create_bucket", resource_type="storage_bucket")
def create_bucket(
    project_id: str,
    bucket_name: str,
    region: str,
    storage_class: str = "STANDARD",
    uniform_bucket_level_access: bool = True,
    versioning_enabled: bool = False,
    labels: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a Cloud Storage bucket.

    When dry_run=True, validates parameters without calling the GCP API.

    Args:
        project_id: GCP project ID.
        bucket_name: Globally unique bucket name.
        region: GCP region (e.g. us-central1).
        storage_class: Storage class (STANDARD or NEARLINE).
        uniform_bucket_level_access: Enforce uniform IAM access.
        versioning_enabled: Enable object versioning.
        labels: GCP resource labels.
        dry_run: If True, validate only — do not call GCP.
    """
    if not bucket_name:
        raise ValueError("bucket_name must not be empty")

    if dry_run:
        logger.info("create_bucket_dry_run", bucket_name=bucket_name, region=region)
        return {"resource_id": None, "status": "DRY_RUN_OK", "dry_run": True}

    storage = _get_storage()
    bucket = storage.bucket(bucket_name)
    bucket.storage_class = storage_class
    bucket.iam_configuration.uniform_bucket_level_access_enabled = uniform_bucket_level_access
    if labels:
        bucket.labels = labels

    new_bucket = storage.create_bucket(bucket, location=region, project=project_id)
    if versioning_enabled:
        new_bucket.versioning_enabled = True
        new_bucket.patch()

    logger.info("create_bucket_succeeded", bucket_name=bucket_name)
    return {"resource_id": f"gs://{bucket_name}", "status": "ACTIVE"}


@mcp.tool()
@gcp_circuit_breaker(tool="delete_bucket", resource_type="storage_bucket")
def delete_bucket(project_id: str, bucket_name: str) -> dict[str, Any]:
    """Delete a Cloud Storage bucket (rollback operation).

    Returns success even if the bucket does not exist.

    Args:
        project_id: GCP project ID.
        bucket_name: Name of the bucket to delete.
    """
    storage = _get_storage()
    try:
        bucket = storage.get_bucket(bucket_name)
        bucket.delete(force=True)
        logger.info("delete_bucket_succeeded", bucket_name=bucket_name)
        return {"status": "DELETED"}
    except Exception as exc:
        if "404" in str(exc) or "does not exist" in str(exc).lower():
            logger.info("delete_bucket_not_found_ignored", bucket_name=bucket_name)
            return {"status": "NOT_FOUND"}
        raise


# ─── VPC tools ────────────────────────────────────────────────────────────────

@mcp.tool()
@gcp_circuit_breaker(tool="get_vpc_status", resource_type="vpc_network")
def get_vpc_status(project_id: str, network_name: str) -> dict[str, Any]:
    """Get the status of a VPC network including its subnets.

    Args:
        project_id: GCP project ID.
        network_name: Name of the VPC network.
    """
    compute = _get_compute()
    try:
        network = (
            compute.networks()
            .get(project=project_id, network=network_name)
            .execute()
        )
        subnetwork_refs: list[str] = network.get("subnetworks", [])
        subnets: list[dict[str, Any]] = []
        for ref in subnetwork_refs:
            parts = ref.split("/")
            if len(parts) >= 2:
                region = parts[-3] if len(parts) >= 3 else ""
                subnet_name = parts[-1]
                try:
                    sub = compute.subnetworks().get(
                        project=project_id, region=region, subnetwork=subnet_name
                    ).execute()
                    subnets.append({
                        "name": sub["name"],
                        "region": region,
                        "cidr": sub.get("ipCidrRange", ""),
                        "private_google_access": sub.get("privateIpGoogleAccess", False),
                    })
                except HttpError:
                    subnets.append({"name": subnet_name, "region": region, "cidr": "", "private_google_access": False})

        routing_config = network.get("routingConfig", {})
        return {
            "resource_type": "vpc_network",
            "resource_name": network["name"],
            "gcp_status": "ACTIVE",
            "metadata": {
                "auto_create_subnetworks": network.get("autoCreateSubnetworks", False),
                "routing_mode": routing_config.get("routingMode", "REGIONAL"),
                "subnet_count": len(subnets),
                "subnets": subnets,
                "creation_timestamp": network.get("creationTimestamp"),
            },
        }
    except HttpError as exc:
        if exc.resp.status == 404:
            return {"gcp_status": "NOT_FOUND", "resource_name": network_name}
        raise


@mcp.tool()
@gcp_circuit_breaker(tool="create_vpc_network", resource_type="vpc_network")
def create_vpc_network(
    project_id: str,
    network_name: str,
    auto_create_subnetworks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a VPC network.

    Args:
        project_id: GCP project ID.
        network_name: Name for the network.
        auto_create_subnetworks: Enable auto-mode subnets (default: False).
        dry_run: If True, validate only — do not call GCP.
    """
    if dry_run:
        logger.info("create_vpc_dry_run", network_name=network_name)
        return {"resource_id": None, "status": "DRY_RUN_OK", "dry_run": True}

    compute = _get_compute()
    body = {"name": network_name, "autoCreateSubnetworks": auto_create_subnetworks}
    operation = compute.networks().insert(project=project_id, body=body).execute()
    _wait_for_global_operation(compute, project_id, operation["name"])
    logger.info("create_vpc_succeeded", network_name=network_name)
    return {"resource_id": network_name, "status": "ACTIVE"}


@mcp.tool()
@gcp_circuit_breaker(tool="create_subnetwork", resource_type="vpc_network")
def create_subnetwork(
    project_id: str,
    region: str,
    subnet_name: str,
    network_name: str,
    ip_cidr_range: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a subnet within a VPC network.

    Args:
        project_id: GCP project ID.
        region: Region for the subnet (e.g. us-central1).
        subnet_name: Name for the subnet.
        network_name: Parent VPC network name.
        ip_cidr_range: CIDR range (e.g. 10.0.0.0/24).
        dry_run: If True, validate only — do not call GCP.
    """
    if dry_run:
        logger.info("create_subnet_dry_run", subnet_name=subnet_name)
        return {"resource_id": None, "status": "DRY_RUN_OK", "dry_run": True}

    compute = _get_compute()
    network_url = f"projects/{project_id}/global/networks/{network_name}"
    body = {
        "name": subnet_name,
        "network": network_url,
        "ipCidrRange": ip_cidr_range,
        "region": f"regions/{region}",
        "privateIpGoogleAccess": True,
    }
    operation = compute.subnetworks().insert(project=project_id, region=region, body=body).execute()
    _wait_for_region_operation(compute, project_id, region, operation["name"])
    logger.info("create_subnetwork_succeeded", subnet_name=subnet_name)
    return {"resource_id": subnet_name, "status": "ACTIVE"}


@mcp.tool()
@gcp_circuit_breaker(tool="delete_vpc_network", resource_type="vpc_network")
def delete_vpc_network(project_id: str, network_name: str) -> dict[str, Any]:
    """Delete a VPC network (rollback operation).

    Args:
        project_id: GCP project ID.
        network_name: Name of the network to delete.
    """
    compute = _get_compute()
    try:
        operation = compute.networks().delete(project=project_id, network=network_name).execute()
        _wait_for_global_operation(compute, project_id, operation["name"])
        logger.info("delete_vpc_succeeded", network_name=network_name)
        return {"status": "DELETED"}
    except HttpError as exc:
        if exc.resp.status == 404:
            return {"status": "NOT_FOUND"}
        raise


# ─── List tool ────────────────────────────────────────────────────────────────

@mcp.tool()
@gcp_circuit_breaker(tool="list_project_resources", resource_type="compute_instance")
def list_project_resources(project_id: str, resource_type: str) -> list[dict[str, Any]]:
    """List all GCP resources of a given type in a project.

    Args:
        project_id: GCP project ID.
        resource_type: One of 'compute_instance', 'storage_bucket', 'vpc_network'.
    """
    if resource_type == "compute_instance":
        return _list_vms(project_id)
    elif resource_type == "storage_bucket":
        return _list_buckets(project_id)
    elif resource_type == "vpc_network":
        return _list_vpcs(project_id)
    else:
        raise ValueError(f"Unsupported resource_type: {resource_type}")


def _list_vms(project_id: str) -> list[dict[str, Any]]:
    compute = _get_compute()
    result = compute.instances().aggregatedList(project=project_id).execute()
    items: list[dict[str, Any]] = []
    for zone_data in result.get("items", {}).values():
        for instance in zone_data.get("instances", []):
            zone = instance.get("zone", "").split("/")[-1]
            items.append({
                "resource_name": instance["name"],
                "resource_type": "compute_instance",
                "gcp_status": instance.get("status", "UNKNOWN"),
                "zone_or_region": zone,
                "key_metadata": instance.get("machineType", "").split("/")[-1],
                "creation_timestamp": instance.get("creationTimestamp"),
            })
    return items


def _list_buckets(project_id: str) -> list[dict[str, Any]]:
    storage = _get_storage()
    items: list[dict[str, Any]] = []
    for bucket in storage.list_buckets(project=project_id):
        items.append({
            "resource_name": bucket.name,
            "resource_type": "storage_bucket",
            "gcp_status": "ACTIVE",
            "zone_or_region": bucket.location.lower() if bucket.location else None,
            "key_metadata": bucket.storage_class or "STANDARD",
            "creation_timestamp": bucket.time_created.isoformat() if bucket.time_created else None,
        })
    return items


def _list_vpcs(project_id: str) -> list[dict[str, Any]]:
    compute = _get_compute()
    result = compute.networks().list(project=project_id).execute()
    items: list[dict[str, Any]] = []
    for network in result.get("items", []):
        items.append({
            "resource_name": network["name"],
            "resource_type": "vpc_network",
            "gcp_status": "ACTIVE",
            "zone_or_region": None,
            "key_metadata": network.get("routingConfig", {}).get("routingMode", "REGIONAL"),
            "creation_timestamp": network.get("creationTimestamp"),
        })
    return items


# ─── GCP operation waiters ────────────────────────────────────────────────────

def _wait_for_zone_operation(compute: Any, project_id: str, zone: str, operation_name: str) -> None:
    import time
    while True:
        result = compute.zoneOperations().get(project=project_id, zone=zone, operation=operation_name).execute()
        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(f"GCP operation failed: {result['error']}")
            return
        time.sleep(2)


def _wait_for_region_operation(compute: Any, project_id: str, region: str, operation_name: str) -> None:
    import time
    while True:
        result = compute.regionOperations().get(project=project_id, region=region, operation=operation_name).execute()
        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(f"GCP operation failed: {result['error']}")
            return
        time.sleep(2)


def _wait_for_global_operation(compute: Any, project_id: str, operation_name: str) -> None:
    import time
    while True:
        result = compute.globalOperations().get(project=project_id, operation=operation_name).execute()
        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(f"GCP operation failed: {result['error']}")
            return
        time.sleep(2)


if __name__ == "__main__":
    import os
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8090"))
    mcp.run(transport="sse")
