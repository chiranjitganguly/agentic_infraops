"""PubSub topic and subscription initialisation.

Creates all required topics and subscriptions if they do not already exist.
Auto-detects PUBSUB_EMULATOR_HOST for local development.

Topics:
  - infraops.provisioning.requests
  - infraops.provisioning.status
  - infraops.audit.events

Subscriptions:
  - infraops-provisioning-requests-vm-sub      (→ provision_vm_dag)
  - infraops-provisioning-requests-bucket-sub  (→ provision_bucket_dag)
  - infraops-provisioning-status-sub           (→ notification service)
  - infraops-audit-events-sub                  (→ audit sink)
"""
from __future__ import annotations

import logging
import os

from google.api_core.exceptions import AlreadyExists
from google.cloud import pubsub_v1

_logger = logging.getLogger(__name__)

_TOPICS = [
    "infraops.provisioning.requests",
    "infraops.provisioning.status",
    "infraops.audit.events",
]

_SUBSCRIPTIONS: list[tuple[str, str]] = [
    ("infraops.provisioning.requests", "infraops-provisioning-requests-vm-sub"),
    ("infraops.provisioning.requests", "infraops-provisioning-requests-bucket-sub"),
    ("infraops.provisioning.status", "infraops-provisioning-status-sub"),
    ("infraops.audit.events", "infraops-audit-events-sub"),
]


def setup_pubsub(project_id: str | None = None) -> None:
    """Create all topics and subscriptions. Safe to call on every service startup."""
    gcp_project = project_id or os.environ.get("GCP_PROJECT_ID")
    if not gcp_project:
        raise RuntimeError("GCP_PROJECT_ID environment variable is not set")

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    for topic_id in _TOPICS:
        topic_path = publisher.topic_path(gcp_project, topic_id)
        try:
            publisher.create_topic(request={"name": topic_path})
            _logger.info("Created PubSub topic", extra={"topic": topic_path})
        except AlreadyExists:
            _logger.debug("PubSub topic already exists", extra={"topic": topic_path})

    for topic_id, subscription_id in _SUBSCRIPTIONS:
        topic_path = publisher.topic_path(gcp_project, topic_id)
        subscription_path = subscriber.subscription_path(gcp_project, subscription_id)
        try:
            subscriber.create_subscription(
                request={
                    "name": subscription_path,
                    "topic": topic_path,
                    "ack_deadline_seconds": 60,
                }
            )
            _logger.info(
                "Created PubSub subscription",
                extra={"subscription": subscription_path, "topic": topic_path},
            )
        except AlreadyExists:
            _logger.debug(
                "PubSub subscription already exists",
                extra={"subscription": subscription_path},
            )

    _logger.info("PubSub setup complete", extra={"project": gcp_project})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_pubsub()
