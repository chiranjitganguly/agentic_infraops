"""Orchestrator Agent A2A contract models.

Channel uses 'web' (not 'chatbot') per domain corrections.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from contracts.schemas.infra_request import ChannelType, IntentType
from contracts.schemas.user_role import UserRoleType


class Outcome(str, Enum):
    routed = "routed"
    clarification_needed = "clarification_needed"
    rejected = "rejected"
    rate_limited = "rate_limited"
    guardrail_violation = "guardrail_violation"
    expired = "expired"


class OrchestratorInput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    raw_input: str = Field(min_length=1)
    channel: ChannelType
    requesting_user: str = Field(min_length=1)
    user_role: UserRoleType
    email_thread_id: str | None = None


class OrchestratorOutput(BaseModel):
    correlation_id: uuid.UUID
    request_id: uuid.UUID
    outcome: Outcome
    intent: IntentType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    clarification_question: str | None = None
    rejection_reason: str | None = None
    sub_agent_result: dict[str, Any] | None = None
