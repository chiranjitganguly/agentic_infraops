"""T048 — Provisioning agent confirmation summary builder.

build_confirmation_summary(params, resource_name, region, zone, resource_type,
                           defaults_applied) → str

Produces a human-readable summary of what will be provisioned, including any
defaults the system applied, and a 20-minute confirmation deadline warning.
"""
from __future__ import annotations

from typing import Any

from agentic_infraops.contracts.agents.provisioning import (
    BucketParameters,
    VMParameters,
    VPCParameters,
)


def build_confirmation_summary(
    params: VMParameters | BucketParameters | VPCParameters | dict[str, Any],
    resource_name: str,
    region: str,
    resource_type: str,
    zone: str | None = None,
    defaults_applied: dict[str, str] | None = None,
) -> str:
    """Build a human-readable confirmation summary for the user to review.

    Includes all resolved parameters, any defaults that were applied automatically,
    and the 20-minute confirmation deadline.

    Args:
        params: Typed resource parameters.
        resource_name: The name of the resource to create.
        region: GCP region.
        resource_type: One of compute_instance, storage_bucket, vpc_network.
        zone: GCP zone (required for compute_instance).
        defaults_applied: Mapping of field → applied default value, for transparency.

    Returns:
        A formatted multi-line confirmation summary string.
    """
    lines: list[str] = []

    if resource_type == "compute_instance" and isinstance(params, VMParameters):
        lines += [
            f"You are about to create a Compute Engine VM with the following configuration:",
            f"  • Name:         {resource_name}",
            f"  • Region:       {region}",
            f"  • Zone:         {zone or f'{region}-a'}",
            f"  • Machine type: {params.machine_type}",
            f"  • Disk size:    {params.disk_size_gb} GB",
            f"  • Image:        {params.image_family} ({params.image_project})",
            f"  • Network:      {params.network}",
        ]
        if params.tags:
            lines.append(f"  • Tags:         {', '.join(params.tags)}")

    elif resource_type == "storage_bucket" and isinstance(params, BucketParameters):
        lines += [
            f"You are about to create a Cloud Storage bucket with the following configuration:",
            f"  • Name:               {resource_name}",
            f"  • Region:             {region}",
            f"  • Storage class:      {params.storage_class}",
            f"  • Uniform access:     {'enabled' if params.uniform_bucket_level_access else 'disabled'}",
            f"  • Versioning:         {'enabled' if params.versioning_enabled else 'disabled'}",
        ]
        if params.labels:
            label_str = ", ".join(f"{k}={v}" for k, v in params.labels.items())
            lines.append(f"  • Labels:             {label_str}")

    elif resource_type == "vpc_network" and isinstance(params, VPCParameters):
        lines += [
            f"You are about to create a VPC network with the following configuration:",
            f"  • Network name:       {resource_name}",
            f"  • Region:             {region}",
            f"  • Subnet name:        {params.subnet_name}",
            f"  • Subnet CIDR:        {params.subnet_cidr}",
            f"  • Auto subnets:       {'yes' if params.auto_create_subnetworks else 'no'}",
        ]

    else:
        lines += [
            f"You are about to provision a {resource_type.replace('_', ' ')}:",
            f"  • Name:   {resource_name}",
            f"  • Region: {region}",
        ]
        if isinstance(params, dict):
            for k, v in params.items():
                lines.append(f"  • {k}: {v}")

    if defaults_applied:
        lines.append("")
        lines.append("Defaults applied (not specified in your request):")
        for field_name, default_value in defaults_applied.items():
            lines.append(f"  • {field_name}: {default_value}")

    lines += [
        "",
        "⚠  This action will create real GCP resources that may incur costs.",
        "   You have 20 minutes to confirm. After that, this request will expire.",
    ]

    return "\n".join(lines)
