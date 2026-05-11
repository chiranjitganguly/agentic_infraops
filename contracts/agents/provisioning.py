"""Provisioning Agent A2A contract models.

Post-confirmation output uses status='queued' (not 'pending') per domain corrections.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts.schemas.provisioning_job import ProvisioningJob, ResourceType
from contracts.schemas.user_role import UserRoleType


class VMParameters(BaseModel):
    machine_type: str = Field(default="e2-standard-4")
    disk_size_gb: int = Field(default=50, ge=10, le=2000)
    image_family: str = Field(default="debian-12")
    image_project: str = Field(default="debian-cloud")
    network: str = Field(default="default")
    tags: list[str] = Field(default_factory=list)


class BucketParameters(BaseModel):
    storage_class: str = Field(default="STANDARD")
    uniform_bucket_level_access: bool = True
    versioning_enabled: bool = False
    labels: dict[str, str] = Field(default_factory=dict)


class VPCParameters(BaseModel):
    auto_create_subnetworks: bool = False
    subnet_name: str = Field(min_length=1)
    subnet_region: str = Field(min_length=1)
    subnet_cidr: str = Field(min_length=1, description="e.g. 10.0.0.0/24")


class ProvisioningInput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    infra_request_id: uuid.UUID
    resource_type: ResourceType
    resource_name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    zone: str | None = None
    parameters: VMParameters | BucketParameters | VPCParameters | dict[str, Any]
    requesting_user: str = Field(min_length=1)
    user_role: UserRoleType
    confirmed: bool = False


class ProvisioningConfirmationOutput(BaseModel):
    """Returned before user confirmation — job is in awaiting_confirmation state."""

    correlation_id: uuid.UUID
    request_id: uuid.UUID
    job_id: uuid.UUID
    status: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    confirmation_summary: str
    idempotency_key: str
    existing_job: dict[str, Any] | None = None
    expires_at: datetime


class ProvisioningQueuedOutput(BaseModel):
    """Returned after user confirmation — job has been published to PubSub."""

    correlation_id: uuid.UUID
    request_id: uuid.UUID
    job_id: uuid.UUID
    status: Literal["queued"] = "queued"
    message: str = "Provisioning job queued. Track progress at /api/v1/jobs/{job_id}/stream"


class ErrorCode(str, Enum):
    validation_error = "VALIDATION_ERROR"
    idempotency_conflict = "IDEMPOTENCY_CONFLICT"
    guardrail_violation = "GUARDRAIL_VIOLATION"
    rate_limit_exceeded = "RATE_LIMIT_EXCEEDED"


class ProvisioningErrorOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["error"] = "error"
    error_code: ErrorCode
    error_message: str
    invalid_fields: list[str] = Field(default_factory=list)
