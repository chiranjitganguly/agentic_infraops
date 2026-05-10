"""T034 — Contract tests for POST /api/v1/requests web API response schemas.

Validates Pydantic schema structure for all provision request response types.
No HTTP server or external services required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agentic_infraops.contracts.agents.provisioning import (
    ErrorCode,
    ProvisioningConfirmationOutput,
    ProvisioningErrorOutput,
    ProvisioningQueuedOutput,
)
from agentic_infraops.contracts.schemas.infra_request import (
    ChannelType,
    InfraRequestCreate,
)
from agentic_infraops.contracts.schemas.user_role import UserRoleType


def _confirmation_payload() -> dict:
    return {
        "correlation_id": uuid.uuid4(),
        "request_id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
        "confirmation_summary": (
            "Create e2-standard-4 VM 'my-vm' in us-central1. "
            "50 GB disk. You have 20 minutes to confirm."
        ),
        "idempotency_key": "compute_instance:my-vm:us-central1",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=20),
    }


@pytest.mark.contract
class TestInfraRequestCreateSchema:
    def test_web_channel_request_valid(self) -> None:
        req = InfraRequestCreate(
            correlation_id=uuid.uuid4(),
            raw_input="Create a VM with 4 CPUs in us-central1",
            channel=ChannelType.web,
            requesting_user="dev@example.com",
            user_role=UserRoleType.developer,
        )
        assert req.channel == ChannelType.web

    def test_channel_enum_excludes_chatbot(self) -> None:
        assert "chatbot" not in {c.value for c in ChannelType}

    def test_channel_enum_has_web_and_email(self) -> None:
        values = {c.value for c in ChannelType}
        assert "web" in values
        assert "email" in values

    def test_email_channel_without_thread_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            InfraRequestCreate(
                correlation_id=uuid.uuid4(),
                raw_input="Create a VM",
                channel=ChannelType.email,
                requesting_user="dev@example.com",
                user_role=UserRoleType.developer,
                # missing email_thread_id and email_message_id
            )

    def test_web_channel_does_not_require_thread_id(self) -> None:
        req = InfraRequestCreate(
            correlation_id=uuid.uuid4(),
            raw_input="Create a bucket in us-east1",
            channel=ChannelType.web,
            requesting_user="dev@example.com",
            user_role=UserRoleType.developer,
        )
        assert req.email_thread_id is None


@pytest.mark.contract
class TestProvisioningConfirmationOutputSchema:
    """202 response body for POST /api/v1/requests with a provision intent."""

    def test_status_is_awaiting_confirmation(self) -> None:
        output = ProvisioningConfirmationOutput(**_confirmation_payload())
        assert output.status == "awaiting_confirmation"

    def test_confirmation_summary_is_required(self) -> None:
        payload = _confirmation_payload()
        del payload["confirmation_summary"]
        with pytest.raises(ValidationError):
            ProvisioningConfirmationOutput(**payload)

    def test_job_id_is_required(self) -> None:
        payload = _confirmation_payload()
        del payload["job_id"]
        with pytest.raises(ValidationError):
            ProvisioningConfirmationOutput(**payload)

    def test_expires_at_is_required(self) -> None:
        payload = _confirmation_payload()
        del payload["expires_at"]
        with pytest.raises(ValidationError):
            ProvisioningConfirmationOutput(**payload)

    def test_idempotency_key_is_required(self) -> None:
        payload = _confirmation_payload()
        del payload["idempotency_key"]
        with pytest.raises(ValidationError):
            ProvisioningConfirmationOutput(**payload)

    def test_existing_job_defaults_to_none(self) -> None:
        output = ProvisioningConfirmationOutput(**_confirmation_payload())
        assert output.existing_job is None

    def test_confirmation_summary_is_non_null_for_valid_provision(self) -> None:
        output = ProvisioningConfirmationOutput(**_confirmation_payload())
        assert output.confirmation_summary is not None
        assert len(output.confirmation_summary) > 0


@pytest.mark.contract
class TestProvisioningQueuedOutputSchema:
    """Returned after user confirmation — job is queued, status is never 'pending'."""

    def test_status_is_queued(self) -> None:
        output = ProvisioningQueuedOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
        )
        assert output.status == "queued"

    def test_status_is_not_pending(self) -> None:
        output = ProvisioningQueuedOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
        )
        assert output.status != "pending"

    def test_message_references_stream_endpoint(self) -> None:
        output = ProvisioningQueuedOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
        )
        assert "stream" in output.message.lower()


@pytest.mark.contract
class TestProvisioningErrorOutputSchema:
    def test_error_output_status_is_error(self) -> None:
        output = ProvisioningErrorOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            error_code=ErrorCode.validation_error,
            error_message="machine_type not in allowed list",
        )
        assert output.status == "error"

    def test_invalid_fields_defaults_to_empty_list(self) -> None:
        output = ProvisioningErrorOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            error_code=ErrorCode.guardrail_violation,
            error_message="Region not allowed",
        )
        assert output.invalid_fields == []

    def test_all_error_codes_are_present(self) -> None:
        values = {e.value for e in ErrorCode}
        assert "VALIDATION_ERROR" in values
        assert "IDEMPOTENCY_CONFLICT" in values
        assert "GUARDRAIL_VIOLATION" in values
        assert "RATE_LIMIT_EXCEEDED" in values
