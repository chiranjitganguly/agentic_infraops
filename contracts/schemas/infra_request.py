"""InfraRequest Pydantic models.

Channel enum uses 'web' (not 'chatbot') per domain corrections.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ChannelType(str, Enum):
    web = "web"
    email = "email"


class IntentType(str, Enum):
    provision = "provision"
    enquiry = "enquiry"
    faq = "faq"


class InfraRequestStatus(str, Enum):
    received = "received"
    classifying = "classifying"
    clarifying = "clarifying"
    awaiting_confirmation = "awaiting_confirmation"
    confirmed = "confirmed"
    rejected = "rejected"
    expired = "expired"
    fulfilled = "fulfilled"
    failed = "failed"


class InfraRequestCreate(BaseModel):
    correlation_id: uuid.UUID
    raw_input: str = Field(min_length=1)
    channel: ChannelType
    requesting_user: str = Field(min_length=1)
    user_role: str
    email_thread_id: str | None = None
    email_message_id: str | None = None

    @model_validator(mode="after")
    def validate_email_fields(self) -> "InfraRequestCreate":
        if self.channel == ChannelType.email:
            if not self.email_thread_id or not self.email_message_id:
                raise ValueError("email_thread_id and email_message_id are required for email channel")
        return self


class InfraRequest(BaseModel):
    id: uuid.UUID
    correlation_id: uuid.UUID
    raw_input: str
    channel: ChannelType
    intent: IntentType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    normalized_params: dict[str, Any] = Field(default_factory=dict)
    requesting_user: str
    user_role: str
    status: InfraRequestStatus
    confirmation_summary: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    expires_at: datetime
    email_thread_id: str | None = None
    email_message_id: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}
