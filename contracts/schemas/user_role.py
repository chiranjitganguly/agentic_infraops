from enum import Enum

from pydantic import BaseModel


class UserRoleType(str, Enum):
    developer = "developer"
    platform_engineer = "platform_engineer"


class DeveloperGuardrails(BaseModel):
    allowed_regions: list[str]
    allowed_machine_types: list[str]
    allowed_storage_classes: list[str]
