"""T071 — Status response formatter: typed metadata → human-readable summary."""
from __future__ import annotations

from contracts.agents.enquiry import (
    BucketMetadata,
    ResourceSummary,
    ResourceType,
    VMMetadata,
    VPCMetadata,
)


def format_status_response(
    metadata: VMMetadata | BucketMetadata | VPCMetadata,
    gcp_status: str,
    resource_name: str,
    resource_type: ResourceType,
    project_id: str = "",
) -> str:
    project_label = f" [project: {project_id}]" if project_id else ""
    if resource_type == ResourceType.compute_instance and isinstance(metadata, VMMetadata):
        ext = f", external IP {metadata.external_ip}" if metadata.external_ip else ", no external IP"
        return (
            f"{resource_name} is {gcp_status} in {metadata.zone} "
            f"({metadata.machine_type}, {metadata.disk_size_gb} GB boot disk{ext}){project_label}."
        )
    elif resource_type == ResourceType.storage_bucket and isinstance(metadata, BucketMetadata):
        versioning = "versioning on" if metadata.versioning_enabled else "versioning off"
        return (
            f"{resource_name} is {gcp_status} in {metadata.location} "
            f"({metadata.storage_class}, {versioning}){project_label}."
        )
    elif resource_type == ResourceType.vpc_network and isinstance(metadata, VPCMetadata):
        return (
            f"{resource_name} is {gcp_status} with {metadata.subnet_count} subnet(s), "
            f"routing mode {metadata.routing_mode}{project_label}."
        )
    return f"{resource_name} is {gcp_status}{project_label}."


def format_list_response(
    resources: list[ResourceSummary],
    resource_type: ResourceType,
    project_id: str = "",
) -> str:
    project_label = f" in project '{project_id}'" if project_id else ""
    if not resources:
        return f"No {resource_type.value.replace('_', ' ')}s found{project_label}."

    type_label = resource_type.value.replace("_", " ")
    lines = [f"Found {len(resources)} {type_label}(s){project_label}:"]
    for r in resources:
        loc = f" [{r.zone_or_region}]" if r.zone_or_region else ""
        lines.append(f"  • {r.resource_name}{loc} — {r.gcp_status} ({r.key_metadata})")
    return "\n".join(lines)
