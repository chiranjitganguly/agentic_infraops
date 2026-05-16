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


_ALL_TOPICS = [
    _TOPIC_PROVISIONING_REQUESTS,
    _TOPIC_PROVISIONING_STATUS,
    _TOPIC_AUDIT_EVENTS,
]

_SUBSCRIPTION_MAP = {
    _TOPIC_PROVISIONING_REQUESTS: f"projects/{_PROJECT_ID}/subscriptions/infraops-provisioning-requests-vm-sub",
}


def _get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        emulator_host = os.environ.get("PUBSUB_EMULATOR_HOST")
        if emulator_host:
            os.environ.setdefault("PUBSUB_EMULATOR_HOST", emulator_host)
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def _ensure_topics_exist() -> None:
    """Create topics and subscriptions in the emulator if they don't exist.

    This is a no-op in production (non-emulator) where topics are pre-provisioned via Terraform.
    """
    if not os.environ.get("PUBSUB_EMULATOR_HOST"):
        return
    publisher = _get_publisher()
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import pubsub_v1 as _ps

    subscriber = _ps.SubscriberClient()
    for topic_path in _ALL_TOPICS:
        try:
            publisher.create_topic(name=topic_path)
            logger.info("pubsub_topic_created", topic=topic_path)
        except AlreadyExists:
            pass
        except Exception as exc:
            logger.warning("pubsub_topic_create_failed", topic=topic_path, error=str(exc))

    for topic_path, sub_path in _SUBSCRIPTION_MAP.items():
        try:
            subscriber.create_subscription(name=sub_path, topic=topic_path, ack_deadline_seconds=60)
            logger.info("pubsub_subscription_created", subscription=sub_path)
        except AlreadyExists:
            pass
        except Exception as exc:
            logger.warning("pubsub_subscription_create_failed", subscription=sub_path, error=str(exc))


def _publish(topic_path: str, data: dict[str, Any]) -> str:
    _ensure_topics_exist()
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
