"""T058 — Notification service: PubSub subscriber → Gmail status emails.

Subscribes to infraops-provisioning-status-sub.
On each ProvisioningStatusEvent: sends a status update email via gmail-mcp.
Deduplicates by (job_id, status) in-memory set.
Does NOT write to PostgreSQL (ADR-0003).
"""
from __future__ import annotations

import asyncio
import json
import os

from google.cloud import pubsub_v1

from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="notification-service")
logger = get_logger("notification-service")

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "infraops-dev")
_SUBSCRIPTION = "infraops-provisioning-status-sub"
_SUBSCRIPTION_PATH = f"projects/{_PROJECT_ID}/subscriptions/{_SUBSCRIPTION}"

_STATUS_EMAIL_TEMPLATES: dict[str, str] = {
    "in_progress": (
        "Hi,\n\nYour provisioning job {job_id} for resource '{resource_name}' is now in progress.\n\n"
        "InfraOps Platform"
    ),
    "retrying": (
        "Hi,\n\nYour provisioning job {job_id} for resource '{resource_name}' encountered an issue "
        "and is being retried (attempt {retry_count}).\n\n"
        "InfraOps Platform"
    ),
    "succeeded": (
        "Hi,\n\nYour provisioning job {job_id} for resource '{resource_name}' succeeded!\n\n"
        "GCP Resource ID: {gcp_resource_id}\n\n"
        "InfraOps Platform"
    ),
    "failed": (
        "Hi,\n\nYour provisioning job {job_id} for resource '{resource_name}' has failed.\n\n"
        "Error: {error_message}\n\n"
        "InfraOps Platform"
    ),
    "rollback": (
        "Hi,\n\nYour provisioning job {job_id} for resource '{resource_name}' failed and rollback "
        "is in progress.\n\n"
        "InfraOps Platform"
    ),
}

_seen: set[tuple[str, str]] = set()


def _build_email_body(event: dict) -> str | None:
    status = event.get("status", "")
    template = _STATUS_EMAIL_TEMPLATES.get(status)
    if template is None:
        return None

    return template.format(
        job_id=event.get("job_id", ""),
        resource_name=event.get("resource_name", "unknown"),
        gcp_resource_id=event.get("gcp_resource_id", "N/A"),
        error_message=event.get("error_message", "Unknown error"),
        retry_count=event.get("retry_count", 0),
    )


def _process_message(message: pubsub_v1.subscriber.message.Message) -> None:
    from mcp_servers.gmail import server as gmail

    try:
        event = json.loads(message.data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("notification_decode_error", error=str(exc))
        message.ack()
        return

    job_id = event.get("job_id", "")
    status = event.get("status", "")
    dedup_key = (job_id, status)

    if dedup_key in _seen:
        logger.info("notification_duplicate_skipped", job_id=job_id, status=status)
        message.ack()
        return

    _seen.add(dedup_key)

    body = _build_email_body(event)
    if body is None:
        logger.info("notification_no_template", job_id=job_id, status=status)
        message.ack()
        return

    requesting_user = event.get("requesting_user", "")
    if not requesting_user:
        logger.warning("notification_no_recipient", job_id=job_id)
        message.ack()
        return

    try:
        gmail.send_email(
            to=requesting_user,
            subject=f"InfraOps: Job {job_id} — {status.replace('_', ' ').title()}",
            body=body,
        )
        logger.info("notification_sent", job_id=job_id, status=status, to=requesting_user)
    except Exception as exc:
        logger.error("notification_send_failed", job_id=job_id, error=str(exc))
        _seen.discard(dedup_key)
        message.nack()
        return

    message.ack()


_TOPIC = "infraops-provisioning-status"
_TOPIC_PATH = f"projects/{_PROJECT_ID}/topics/{_TOPIC}"


def _ensure_subscription() -> None:
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    try:
        publisher.get_topic(request={"topic": _TOPIC_PATH})
    except Exception:
        publisher.create_topic(request={"name": _TOPIC_PATH})
        logger.info("pubsub_topic_created", topic=_TOPIC_PATH)

    try:
        subscriber.get_subscription(request={"subscription": _SUBSCRIPTION_PATH})
    except Exception:
        subscriber.create_subscription(
            request={"name": _SUBSCRIPTION_PATH, "topic": _TOPIC_PATH}
        )
        logger.info("pubsub_subscription_created", subscription=_SUBSCRIPTION_PATH)


def run_notification_service() -> None:
    _ensure_subscription()

    subscriber = pubsub_v1.SubscriberClient()

    logger.info("notification_service_started", subscription=_SUBSCRIPTION_PATH)

    streaming_pull_future = subscriber.subscribe(
        _SUBSCRIPTION_PATH,
        callback=_process_message,
    )

    with subscriber:
        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            streaming_pull_future.result()
            logger.info("notification_service_stopped")


if __name__ == "__main__":
    run_notification_service()
