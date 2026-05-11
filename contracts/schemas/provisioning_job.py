"""ProvisioningJob Pydantic models.

JobStatus uses 'awaiting_confirmation' + 'queued' — never 'pending'.
rollback_resources starts as empty list and is appended after each successful GCP create.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    awaiting_confirmation = "awaiting_confirmation"
    queued = "queued"
    in_progress = "in_progress"
    retrying = "retrying"
    rollback = "rollback"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled)


class ResourceType(str, Enum):
    compute_instance = "compute_instance"
    storage_bucket = "storage_bucket"
    vpc_network = "vpc_network"


class RollbackResource(BaseModel):
    """A single GCP resource that was successfully created and must be deleted on rollback."""

    resource_type: ResourceType
    resource_name: str
    region: str
    zone: str | None = None
    gcp_resource_id: str


class ProvisioningJobCreate(BaseModel):
    infra_request_id: uuid.UUID
    correlation_id: uuid.UUID
    idempotency_key: str = Field(min_length=1)
    resource_type: ResourceType
    resource_name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    zone: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    requesting_user: str = Field(min_length=1)
    dry_run: bool = False


class ProvisioningJob(BaseModel):
    id: uuid.UUID
    infra_request_id: uuid.UUID
    correlation_id: uuid.UUID
    idempotency_key: str
    resource_type: ResourceType
    resource_name: str
    region: str
    zone: str | None = None
    parameters: dict[str, Any]
    status: JobStatus
    retry_count: int = Field(ge=0, le=3)
    gcp_resource_id: str | None = None
    rollback_resources: list[RollbackResource] = Field(default_factory=list)
    error_message: str | None = None
    requesting_user: str
    dry_run: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
