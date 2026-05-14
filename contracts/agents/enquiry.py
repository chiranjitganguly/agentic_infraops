"""Enquiry Agent A2A contract models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Union

from pydantic import BaseModel, Field

from contracts.schemas.provisioning_job import ResourceType
from contracts.schemas.user_role import UserRoleType


# ─── Typed metadata per resource type ────────────────────────────────────────

class SubnetSummary(BaseModel):
    name: str
    region: str
    cidr: str
    private_google_access: bool


class VMMetadata(BaseModel):
    machine_type: str
    zone: str
    network: str
    subnetwork: str | None = None
    internal_ip: str | None = None
    external_ip: str | None = None
    disk_size_gb: int
    creation_timestamp: datetime | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class BucketMetadata(BaseModel):
    storage_class: str
    location: str
    location_type: str
    versioning_enabled: bool
    uniform_bucket_level_access: bool
    public_access_prevention: str
    creation_time: datetime | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class VPCMetadata(BaseModel):
    auto_create_subnetworks: bool
    routing_mode: str
    subnet_count: int
    subnets: list[SubnetSummary] = Field(default_factory=list)
    creation_timestamp: datetime | None = None


ResourceMetadata = Union[VMMetadata, BucketMetadata, VPCMetadata]


class ResourceSummary(BaseModel):
    resource_name: str
    resource_type: ResourceType
    gcp_status: str
    zone_or_region: str | None = None
    key_metadata: str
    creation_timestamp: datetime | None = None


# ─── Agent I/O schemas ────────────────────────────────────────────────────────

class EnquiryInput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    query_type: Literal["single", "list"] = "single"
    resource_type: ResourceType
    resource_name: str | None = Field(default=None)
    project_id: str = Field(min_length=1)
    zone: str | None = None
    region: str | None = None
    requesting_user: str = Field(min_length=1)
    user_role: UserRoleType


class EnquiryFoundOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["found"] = "found"
    query_type: Literal["single"] = "single"
    resource_type: ResourceType
    resource_name: str
    gcp_status: str
    metadata: ResourceMetadata
    human_readable_summary: str
    queried_at: datetime


class EnquiryListOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    status: Literal["listed"] = "listed"
    query_type: Literal["list"] = "list"
    resource_type: ResourceType
    project_id: str
    resources: list[ResourceSummary] = Field(default_factory=list)
    total_count: int
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


EnquiryOutput = Union[
    EnquiryFoundOutput,
    EnquiryListOutput,
    EnquiryNotFoundOutput,
    EnquiryAccessDeniedOutput,
]
