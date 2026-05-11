"""Correlation context propagation for A2A HTTP calls.

Uses Python contextvars so context is per-async-task without thread-safety issues.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

_HEADER_CORRELATION_ID = "X-Correlation-ID"
_HEADER_REQUEST_ID = "X-Request-ID"


@dataclass
class CorrelationContext:
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    request_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def new_request(self) -> "CorrelationContext":
        """Return a new context with the same correlation_id but a fresh request_id."""
        return CorrelationContext(
            correlation_id=self.correlation_id,
            request_id=uuid.uuid4(),
        )

    @classmethod
    def from_ids(cls, correlation_id: uuid.UUID, request_id: uuid.UUID) -> "CorrelationContext":
        """Propagate existing IDs rather than generating new ones (use when forwarding a request)."""
        return cls(correlation_id=correlation_id, request_id=request_id)


_context_var: ContextVar[CorrelationContext] = ContextVar(
    "correlation_context",
    default=CorrelationContext(),
)


def get_correlation_context() -> CorrelationContext:
    return _context_var.get()


def set_correlation_context(ctx: CorrelationContext) -> None:
    _context_var.set(ctx)


def new_correlation_context() -> CorrelationContext:
    ctx = CorrelationContext()
    _context_var.set(ctx)
    return ctx


def inject_correlation_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Return headers dict with correlation fields injected (for outgoing A2A calls)."""
    ctx = get_correlation_context()
    out = dict(headers or {})
    out[_HEADER_CORRELATION_ID] = str(ctx.correlation_id)
    out[_HEADER_REQUEST_ID] = str(ctx.request_id)
    return out


def extract_correlation_headers(headers: dict[str, Any]) -> CorrelationContext:
    """Parse correlation IDs from incoming request headers and set the context var."""

    def _get(key: str) -> str | None:
        return headers.get(key) or headers.get(key.lower())

    raw_correlation = _get(_HEADER_CORRELATION_ID)
    raw_request = _get(_HEADER_REQUEST_ID)

    ctx = CorrelationContext(
        correlation_id=uuid.UUID(raw_correlation) if raw_correlation else uuid.uuid4(),
        request_id=uuid.UUID(raw_request) if raw_request else uuid.uuid4(),
    )
    _context_var.set(ctx)
    return ctx
