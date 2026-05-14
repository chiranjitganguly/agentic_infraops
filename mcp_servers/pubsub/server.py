"""T037 — pubsub-mcp: MCP server wrapping Cloud PubSub publish operations.

Tools: publish_provisioning_request, publish_status_event, publish_audit_event.
Routes to PubSub emulator automatically when PUBSUB_EMULATOR_HOST is set.
"""
from __future__ import annotations

import json
import os
from typing import Any

from google.cloud import pubsub_v1
from mcp.server.fastmcp import FastMCP

from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="pubsub-mcp")
logger = get_logger("pubsub-mcp")

mcp = FastMCP("pubsub-mcp")

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "local-dev")
_TOPIC_PROVISIONING_REQUESTS = f"projects/{_PROJECT_ID}/topics/infraops.provisioning.requests"
_TOPIC_PROVISIONING_STATUS = f"projects/{_PROJECT_ID}/topics/infraops.provisioning.status"
_TOPIC_AUDIT_EVENTS = f"projects/{_PROJECT_ID}/topics/infraops.audit.events"

_publisher: pubsub_v1.PublisherClient | None = None


def _get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        emulator_host = os.environ.get("PUBSUB_EMULATOR_HOST")
        if emulator_host:
            os.environ.setdefault("PUBSUB_EMULATOR_HOST", emulator_host)
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def _publish(topic_path: str, data: dict[str, Any]) -> str:
    publisher = _get_publisher()
    message_bytes = json.dumps(data, default=str).encode("utf-8")
    future = publisher.publish(topic_path, message_bytes)
    message_id: str = future.result(timeout=10)
    logger.info("pubsub_published", topic=topic_path, message_id=message_id)
    return message_id


@mcp.tool()
def publish_provisioning_request(event: dict[str, Any]) -> dict[str, str]:
    """Publish a ProvisioningRequestEvent to infraops.provisioning.requests.

    Args:
        event: Serialised ProvisioningRequestEvent dict (schema_version 1.0.0 required).
    """
    if event.get("schema_version") != "1.0.0":
        raise ValueError(f"Unsupported schema_version: {event.get('schema_version')}")
    message_id = _publish(_TOPIC_PROVISIONING_REQUESTS, event)
    return {"message_id": message_id}


@mcp.tool()
def publish_status_event(event: dict[str, Any]) -> dict[str, str]:
    """Publish a ProvisioningStatusEvent to infraops.provisioning.status.

    Args:
        event: Serialised ProvisioningStatusEvent dict (schema_version 1.0.0 required).
    """
    if event.get("schema_version") != "1.0.0":
        raise ValueError(f"Unsupported schema_version: {event.get('schema_version')}")
    message_id = _publish(_TOPIC_PROVISIONING_STATUS, event)
    return {"message_id": message_id}


@mcp.tool()
def publish_audit_event(event: dict[str, Any]) -> dict[str, str]:
    """Publish an AuditEventMessage to infraops.audit.events.

    Args:
        event: Serialised AuditEventMessage dict (schema_version 1.0.0 required).
    """
    if event.get("schema_version") != "1.0.0":
        raise ValueError(f"Unsupported schema_version: {event.get('schema_version')}")
    message_id = _publish(_TOPIC_AUDIT_EVENTS, event)
    return {"message_id": message_id}


if __name__ == "__main__":
    import os
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8091"))
    mcp.run(transport="sse")
