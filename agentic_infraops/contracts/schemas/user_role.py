"""UserRole Pydantic models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class UserRoleType(str, Enum):
    developer = "developer"
    platform_engineer = "platform_engineer"


class DeveloperGuardrails(BaseModel):
    """Allowed resource parameters for developer-role users. Platform engineers are unrestricted."""

    allowed_regions: list[str] = Field(
        default=["us-central1", "us-east1", "europe-west1"],
        description="GCP regions developers may provision into",
    )
    allowed_machine_types: list[str] = Field(
        default=["e2-standard-2", "e2-standard-4", "e2-standard-8"],
        description="VM machine types developers may request",
    )
    allowed_storage_classes: list[str] = Field(
        default=["STANDARD", "NEARLINE"],
        description="Cloud Storage classes developers may request",
    )
    daily_provisioning_limit: int = Field(
        default=10,
        description="Maximum provisioning jobs a developer may submit per calendar day (UTC)",
    )
    vpc_provisioning_allowed: bool = Field(
        default=False,
        description="Developers may not provision VPC networks",
    )


class UserRole(BaseModel):
    user_id: str
    role: UserRoleType
    api_key_hash: str = Field(exclude=True)
    api_key_expires_at: datetime
    api_key_last_used: datetime | None = None
    daily_provisioning_count: int = 0
    daily_count_reset_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @property
    def guardrails(self) -> DeveloperGuardrails | None:
        """Returns default developer guardrails for developer role; None for platform engineer."""
        if self.role == UserRoleType.developer:
            return DeveloperGuardrails()
        return None
