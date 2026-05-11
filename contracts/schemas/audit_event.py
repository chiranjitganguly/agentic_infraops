"""AuditEvent Pydantic models — append-only, 21 event types."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    request_received = "request_received"
    intent_classified = "intent_classified"
    clarification_requested = "clarification_requested"
    confirmation_sent = "confirmation_sent"
    request_confirmed = "request_confirmed"
    request_rejected = "request_rejected"
    request_expired = "request_expired"
    guardrail_violation = "guardrail_violation"
    rate_limit_exceeded = "rate_limit_exceeded"
    job_created = "job_created"
    job_started = "job_started"
    job_retried = "job_retried"
    job_succeeded = "job_succeeded"
    job_failed = "job_failed"
    job_cancelled = "job_cancelled"
    rollback_started = "rollback_started"
    rollback_completed = "rollback_completed"
    status_queried = "status_queried"
    faq_answered = "faq_answered"
    backstage_registered = "backstage_registered"
    # 21st event type
    api_key_rotated = "api_key_rotated"


_REDACTED_FIELDS = frozenset({"api_key", "api_key_hash", "password", "secret", "token"})


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Replace sensitive field values with '[REDACTED]' recursively."""
    result: dict[str, Any] = {}
    for k, v in payload.items():
        if k in _REDACTED_FIELDS:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_payload(v)
        else:
            result[k] = v
    return result


class AuditEventCreate(BaseModel):
    event_type: AuditEventType
    actor: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    workflow_name: str | None = None
    resource_type: str | None = None
    resource_name: str | None = None
    intent: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: uuid.UUID
    request_id: uuid.UUID

    def model_post_init(self, __context: Any) -> None:
        self.payload = redact_payload(self.payload)


class AuditEvent(BaseModel):
    id: uuid.UUID
    event_type: AuditEventType
    actor: str
    agent_name: str
    workflow_name: str | None = None
    resource_type: str | None = None
    resource_name: str | None = None
    intent: str | None = None
    payload: dict[str, Any]
    timestamp: datetime
    correlation_id: uuid.UUID
    request_id: uuid.UUID

    model_config = {"from_attributes": True}
