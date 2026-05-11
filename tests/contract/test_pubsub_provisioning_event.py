"""T033 — Contract tests for ProvisioningRequestEvent PubSub schema (v1.0.0).

These tests MUST fail before the schema is implemented, and pass after.
No external services required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.events.pubsub_events import (
    ProvisioningRequestEvent,
    ProvisioningStatusEvent,
)
from contracts.schemas.provisioning_job import JobStatus, ResourceType
from contracts.schemas.user_role import UserRoleType


def _request_event_payload() -> dict:
    return {
        "job_id": uuid.uuid4(),
        "infra_request_id": uuid.uuid4(),
        "correlation_id": uuid.uuid4(),
        "idempotency_key": "compute_instance:my-vm:us-central1",
        "resource_type": ResourceType.compute_instance,
        "resource_name": "my-vm",
        "region": "us-central1",
        "requesting_user": "dev@example.com",
        "user_role": UserRoleType.developer,
        "published_at": datetime.now(timezone.utc),
    }


@pytest.mark.contract
class TestProvisioningRequestEventSchema:
    def test_schema_version_is_1_0_0(self) -> None:
        event = ProvisioningRequestEvent(**_request_event_payload())
        assert event.schema_version == "1.0.0"

    def test_event_type_is_fixed_literal(self) -> None:
        event = ProvisioningRequestEvent(**_request_event_payload())
        assert event.event_type == "provisioning.request.created"

    def test_all_required_fields_accepted(self) -> None:
        event = ProvisioningRequestEvent(**_request_event_payload())
        assert event.job_id is not None
        assert event.infra_request_id is not None
        assert event.correlation_id is not None
        assert event.idempotency_key
        assert event.resource_name
        assert event.region
        assert event.requesting_user

    def test_missing_job_id_raises(self) -> None:
        payload = _request_event_payload()
        del payload["job_id"]
        with pytest.raises(ValidationError):
            ProvisioningRequestEvent(**payload)

    def test_missing_infra_request_id_raises(self) -> None:
        payload = _request_event_payload()
        del payload["infra_request_id"]
        with pytest.raises(ValidationError):
            ProvisioningRequestEvent(**payload)

    def test_empty_idempotency_key_raises(self) -> None:
        payload = _request_event_payload()
        payload["idempotency_key"] = ""
        with pytest.raises(ValidationError):
            ProvisioningRequestEvent(**payload)

    def test_empty_resource_name_raises(self) -> None:
        payload = _request_event_payload()
        payload["resource_name"] = ""
        with pytest.raises(ValidationError):
            ProvisioningRequestEvent(**payload)

    def test_empty_region_raises(self) -> None:
        payload = _request_event_payload()
        payload["region"] = ""
        with pytest.raises(ValidationError):
            ProvisioningRequestEvent(**payload)

    def test_dry_run_defaults_to_false(self) -> None:
        event = ProvisioningRequestEvent(**_request_event_payload())
        assert event.dry_run is False

    def test_zone_is_optional(self) -> None:
        event = ProvisioningRequestEvent(**_request_event_payload())
        assert event.zone is None

    def test_parameters_defaults_to_empty_dict(self) -> None:
        event = ProvisioningRequestEvent(**_request_event_payload())
        assert event.parameters == {}

    @pytest.mark.parametrize("resource_type", list(ResourceType))
    def test_all_resource_types_accepted(self, resource_type: ResourceType) -> None:
        payload = _request_event_payload()
        payload["resource_type"] = resource_type
        event = ProvisioningRequestEvent(**payload)
        assert event.resource_type == resource_type

    def test_schema_version_cannot_be_overridden(self) -> None:
        payload = _request_event_payload()
        payload["schema_version"] = "2.0.0"
        with pytest.raises(ValidationError):
            ProvisioningRequestEvent(**payload)


@pytest.mark.contract
class TestJobStatusExcludesPending:
    """Guarantee: 'pending' is not a valid JobStatus — uses awaiting_confirmation + queued."""

    def test_pending_is_not_a_valid_job_status(self) -> None:
        assert "pending" not in {s.value for s in JobStatus}

    def test_awaiting_confirmation_is_valid(self) -> None:
        assert "awaiting_confirmation" in {s.value for s in JobStatus}

    def test_queued_is_valid(self) -> None:
        assert "queued" in {s.value for s in JobStatus}

    def test_all_expected_statuses_present(self) -> None:
        values = {s.value for s in JobStatus}
        expected = {
            "awaiting_confirmation",
            "queued",
            "in_progress",
            "retrying",
            "rollback",
            "succeeded",
            "failed",
            "cancelled",
        }
        assert expected.issubset(values)

    def test_provisioning_status_event_rejects_pending(self) -> None:
        with pytest.raises(ValidationError):
            ProvisioningStatusEvent(
                job_id=uuid.uuid4(),
                infra_request_id=uuid.uuid4(),
                correlation_id=uuid.uuid4(),
                idempotency_key="compute_instance:vm:us-central1",
                resource_type=ResourceType.compute_instance,
                resource_name="vm",
                status="pending",  # type: ignore[arg-type]
                retry_count=0,
                requesting_user="dev@example.com",
                published_at=datetime.now(timezone.utc),
            )

    def test_retry_count_upper_bound_is_3(self) -> None:
        with pytest.raises(ValidationError):
            ProvisioningStatusEvent(
                job_id=uuid.uuid4(),
                infra_request_id=uuid.uuid4(),
                correlation_id=uuid.uuid4(),
                idempotency_key="compute_instance:vm:us-central1",
                resource_type=ResourceType.compute_instance,
                resource_name="vm",
                status=JobStatus.in_progress,
                retry_count=4,
                requesting_user="dev@example.com",
                published_at=datetime.now(timezone.utc),
            )

    def test_job_status_is_terminal_helper(self) -> None:
        assert JobStatus.succeeded.is_terminal
        assert JobStatus.failed.is_terminal
        assert JobStatus.cancelled.is_terminal
        assert not JobStatus.in_progress.is_terminal
        assert not JobStatus.queued.is_terminal
