"""Enquiry Agent A2A contract models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts.schemas.provisioning_job import ResourceType
from contracts.schemas.user_role import UserRoleType


class EnquiryInput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    resource_type: ResourceType
    resource_name: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    zone: str | None = None
    region: str | None = None
    requesting_user: str = Field(min_length=1)
    user_role: UserRoleType


class EnquiryFoundOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["found"] = "found"
    resource_type: ResourceType
    resource_name: str
    gcp_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_readable_summary: str
    queried_at: datetime


class EnquiryNotFoundOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["not_found"] = "not_found"
    resource_type: ResourceType
    resource_name: str
    message: str


class EnquiryAccessDeniedOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["access_denied"] = "access_denied"
    message: str = "You do not have permission to view this resource."
