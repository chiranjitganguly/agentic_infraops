"""Structured logging setup using structlog.

Outputs JSON with mandatory fields: correlation_id, request_id, agent_name,
workflow_name, timestamp. Sensitive fields are redacted before emission.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_REDACTED_FIELDS = frozenset({
    "api_key",
    "api_key_hash",
    "password",
    "token",
    "secret",
    "authorization",
})


def _redact_sensitive(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for field in _REDACTED_FIELDS:
        if field in event_dict:
            event_dict[field] = "[REDACTED]"
    return event_dict


def configure_logging(
    service_name: str,
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Call once at service startup to configure structlog JSON output."""
    log_level_int = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_sensitive,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level_int)

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_request_context(
    correlation_id: str,
    request_id: str,
    agent_name: str = "",
    workflow_name: str | None = None,
) -> None:
    """Bind per-request fields to structlog context vars (call at request ingress)."""
    ctx: dict[str, Any] = {
        "correlation_id": correlation_id,
        "request_id": request_id,
    }
    if agent_name:
        ctx["agent_name"] = agent_name
    if workflow_name:
        ctx["workflow_name"] = workflow_name
    structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
