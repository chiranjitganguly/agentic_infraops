"""PubSub event Pydantic models — schema v1.0.0.

Additive-only evolution: new optional fields may be added.
Field removals and type changes require a major version bump + new topic.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentic_infraops.contracts.schemas.provisioning_job import JobStatus, ResourceType
from agentic_infraops.contracts.schemas.user_role import UserRoleType


class ProvisioningRequestEvent(BaseModel):
    """Published to infraops.provisioning.requests by the Provisioning Agent."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_type: Literal["provisioning.request.created"] = "provisioning.request.created"
    job_id: uuid.UUID
    infra_request_id: uuid.UUID
    correlation_id: uuid.UUID
    idempotency_key: str = Field(min_length=1)
    resource_type: ResourceType
    resource_name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    zone: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    requesting_user: str = Field(min_length=1)
    user_role: UserRoleType
    dry_run: bool = False
    published_at: datetime


class ProvisioningStatusEvent(BaseModel):
    """Published to infraops.provisioning.status by Airflow DAGs."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_type: Literal["provisioning.job.status_changed"] = "provisioning.job.status_changed"
    job_id: uuid.UUID
    infra_request_id: uuid.UUID
    correlation_id: uuid.UUID
    idempotency_key: str
    resource_type: ResourceType
    resource_name: str
    status: JobStatus
    retry_count: int = Field(ge=0, le=3)
    gcp_resource_id: str | None = None
    error_message: str | None = None
    requesting_user: str
    published_at: datetime


class AuditEventMessage(BaseModel):
    """Published to infraops.audit.events by all agents and Airflow DAGs.

    Sensitive fields MUST be redacted before publishing (see AuditEventCreate.redact_payload).
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    workflow_name: str | None = None
    resource_type: str | None = None
    resource_name: str | None = None
    intent: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    correlation_id: uuid.UUID
    request_id: uuid.UUID
