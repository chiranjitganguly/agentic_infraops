"""Shared audit event emission helper.

Single function that all agents call to emit audit events via postgres-mcp.
Accepts an injectable postgres client so tests can pass stubs without patching.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from contracts.schemas.audit_event import AuditEventCreate, AuditEventType
from contracts.shared.logging import get_logger

logger = get_logger("audit")


class _AuditPostgresClient(Protocol):
    async def create_audit_event(self, event_data: dict) -> dict: ...


async def emit_audit_event(
    *,
    event_type: AuditEventType,
    actor: str,
    agent_name: str,
    resource_type: str | None = None,
    resource_name: str | None = None,
    correlation_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    postgres: _AuditPostgresClient,
) -> None:
    """Emit a typed audit event via the postgres MCP server.

    Swallows exceptions so audit failures never interrupt the caller's flow.
    """
    try:
        event = AuditEventCreate(
            event_type=event_type,
            actor=actor,
            agent_name=agent_name,
            resource_type=resource_type,
            resource_name=resource_name,
            payload=payload or {},
            correlation_id=correlation_id,
            request_id=request_id,
        )
        await postgres.create_audit_event(event.model_dump())
    except Exception as exc:
        logger.warning("audit_event_failed", error=str(exc), event_type=event_type.value)
