"""T070 — Status query skill: single-resource lookup and project-wide listing."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from contracts.agents.enquiry import (
    BucketMetadata,
    ResourceSummary,
    ResourceType,
    SubnetSummary,
    VMMetadata,
    VPCMetadata,
)
from contracts.shared.logging import get_logger

logger = get_logger("status-query-skill")

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")


def _resource_mcp() -> object:
    from mcp_servers.gcp_resource import server
    return server


def query_resource_status(
    resource_type: ResourceType,
    resource_name: str,
    project_id: str,
    zone: str | None = None,
    region: str | None = None,
) -> dict:
    """Query live GCP status for a single named resource.

    Returns a dict with keys: resource_type, resource_name, gcp_status, metadata, queried_at.
    metadata is a typed VMMetadata | BucketMetadata | VPCMetadata object.
    Raises ValueError if the resource is NOT_FOUND.
    """
    mcp = _resource_mcp()
    project_id = project_id or _PROJECT_ID

    if resource_type == ResourceType.compute_instance:
        if not zone:
            raise ValueError("zone is required for compute_instance status queries")
        raw = mcp.get_vm_status(project_id=project_id, zone=zone, instance_name=resource_name)
    elif resource_type == ResourceType.storage_bucket:
        raw = mcp.get_bucket_status(project_id=project_id, bucket_name=resource_name)
    elif resource_type == ResourceType.vpc_network:
        raw = mcp.get_vpc_status(project_id=project_id, network_name=resource_name)
    else:
        raise ValueError(f"Unsupported resource_type: {resource_type}")

    gcp_status = raw.get("gcp_status", "UNKNOWN")
    if gcp_status == "NOT_FOUND":
        return {"not_found": True, "resource_name": resource_name, "resource_type": resource_type}

    raw_meta = raw.get("metadata", {})
    metadata = _parse_metadata(resource_type, raw_meta)

    return {
        "resource_type": resource_type,
        "resource_name": raw.get("resource_name", resource_name),
        "gcp_status": gcp_status,
        "metadata": metadata,
        "queried_at": datetime.now(timezone.utc),
    }


def list_resources(resource_type: ResourceType, project_id: str) -> list[ResourceSummary]:
    """List all GCP resources of the given type in the project."""
    mcp = _resource_mcp()
    project_id = project_id or _PROJECT_ID

    raw_list: list[dict] = mcp.list_project_resources(
        project_id=project_id,
        resource_type=resource_type.value,
    )

    summaries: list[ResourceSummary] = []
    for item in raw_list:
        creation_raw = item.get("creation_timestamp")
        summaries.append(ResourceSummary(
            resource_name=item["resource_name"],
            resource_type=ResourceType(item["resource_type"]),
            gcp_status=item.get("gcp_status", "UNKNOWN"),
            zone_or_region=item.get("zone_or_region"),
            key_metadata=item.get("key_metadata", ""),
            creation_timestamp=_parse_dt(creation_raw),
        ))
    return summaries


def _parse_metadata(
    resource_type: ResourceType,
    raw: dict,
) -> VMMetadata | BucketMetadata | VPCMetadata:
    if resource_type == ResourceType.compute_instance:
        return VMMetadata(
            machine_type=raw.get("machine_type", ""),
            zone=raw.get("zone", ""),
            network=raw.get("network", ""),
            subnetwork=raw.get("subnetwork"),
            internal_ip=raw.get("internal_ip"),
            external_ip=raw.get("external_ip"),
            disk_size_gb=raw.get("disk_size_gb", 50),
            creation_timestamp=_parse_dt(raw.get("creation_timestamp")),
            labels=raw.get("labels", {}),
        )
    elif resource_type == ResourceType.storage_bucket:
        return BucketMetadata(
            storage_class=raw.get("storage_class", "STANDARD"),
            location=raw.get("location", ""),
            location_type=raw.get("location_type", "region"),
            versioning_enabled=raw.get("versioning_enabled", False),
            uniform_bucket_level_access=raw.get("uniform_bucket_level_access", True),
            public_access_prevention=raw.get("public_access_prevention", "enforced"),
            creation_time=_parse_dt(raw.get("creation_time")),
            labels=raw.get("labels", {}),
        )
    else:
        subnets = [
            SubnetSummary(
                name=s.get("name", ""),
                region=s.get("region", ""),
                cidr=s.get("cidr", ""),
                private_google_access=s.get("private_google_access", False),
            )
            for s in raw.get("subnets", [])
        ]
        return VPCMetadata(
            auto_create_subnetworks=raw.get("auto_create_subnetworks", False),
            routing_mode=raw.get("routing_mode", "REGIONAL"),
            subnet_count=raw.get("subnet_count", len(subnets)),
            subnets=subnets,
            creation_timestamp=_parse_dt(raw.get("creation_timestamp")),
        )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
