"""T068 — Contract tests for Enquiry Agent A2A input/output schemas.

Validates EnquiryInput, EnquiryFoundOutput, EnquiryListOutput,
EnquiryNotFoundOutput, and EnquiryAccessDeniedOutput schemas.
No external services required.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.agents.enquiry import (
    EnquiryAccessDeniedOutput,
    EnquiryFoundOutput,
    EnquiryInput,
    EnquiryListOutput,
    EnquiryNotFoundOutput,
    ResourceSummary,
    VMMetadata,
)
from contracts.schemas.provisioning_job import ResourceType
from contracts.schemas.user_role import UserRoleType


def _base_input(**overrides) -> dict:  # type: ignore[no-untyped-def]
    base = {
        "correlation_id": uuid.uuid4(),
        "request_id": uuid.uuid4(),
        "query_type": "single",
        "resource_type": ResourceType.compute_instance,
        "resource_name": "vm-123",
        "project_id": "agentic-infraops",
        "requesting_user": "dev@example.com",
        "user_role": UserRoleType.developer,
    }
    base.update(overrides)
    return base


def _vm_metadata() -> VMMetadata:
    return VMMetadata(
        machine_type="e2-standard-4",
        zone="us-central1-a",
        network="global/networks/default",
        disk_size_gb=50,
    )


@pytest.mark.contract
class TestEnquiryInputSchema:
    def test_valid_single_query(self) -> None:
        inp = EnquiryInput(**_base_input())
        assert inp.query_type == "single"
        assert inp.resource_name == "vm-123"

    def test_list_query_resource_name_nullable(self) -> None:
        inp = EnquiryInput(**_base_input(query_type="list", resource_name=None))
        assert inp.query_type == "list"
        assert inp.resource_name is None

    def test_zone_and_region_optional(self) -> None:
        inp = EnquiryInput(**_base_input())
        assert inp.zone is None
        assert inp.region is None

    def test_zone_can_be_set(self) -> None:
        inp = EnquiryInput(**_base_input(zone="us-central1-a"))
        assert inp.zone == "us-central1-a"

    def test_all_resource_types_accepted(self) -> None:
        for rt in ResourceType:
            inp = EnquiryInput(**_base_input(resource_type=rt))
            assert inp.resource_type == rt

    def test_empty_project_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnquiryInput(**_base_input(project_id=""))

    def test_empty_requesting_user_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnquiryInput(**_base_input(requesting_user=""))

    def test_missing_correlation_id_raises(self) -> None:
        payload = _base_input()
        del payload["correlation_id"]
        with pytest.raises(ValidationError):
            EnquiryInput(**payload)

    def test_missing_request_id_raises(self) -> None:
        payload = _base_input()
        del payload["request_id"]
        with pytest.raises(ValidationError):
            EnquiryInput(**payload)

    def test_both_user_roles_accepted(self) -> None:
        for role in UserRoleType:
            inp = EnquiryInput(**_base_input(user_role=role))
            assert inp.user_role == role

    def test_query_type_defaults_to_single(self) -> None:
        payload = _base_input()
        del payload["query_type"]
        inp = EnquiryInput(**payload)
        assert inp.query_type == "single"


@pytest.mark.contract
class TestEnquiryFoundOutputSchema:
    def test_valid_found_output(self) -> None:
        now = datetime.now(timezone.utc)
        output = EnquiryFoundOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.compute_instance,
            resource_name="vm-123",
            gcp_status="RUNNING",
            metadata=_vm_metadata(),
            human_readable_summary="vm-123 is RUNNING in us-central1-a (e2-standard-4).",
            queried_at=now,
        )
        assert output.status == "found"
        assert output.gcp_status == "RUNNING"
        assert output.human_readable_summary != ""
        assert output.queried_at is not None

    def test_query_type_is_single(self) -> None:
        output = EnquiryFoundOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.compute_instance,
            resource_name="vm-123",
            gcp_status="RUNNING",
            metadata=_vm_metadata(),
            human_readable_summary="vm-123 is RUNNING.",
            queried_at=datetime.now(timezone.utc),
        )
        assert output.query_type == "single"

    def test_metadata_is_typed_vm_metadata(self) -> None:
        output = EnquiryFoundOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.compute_instance,
            resource_name="vm-123",
            gcp_status="RUNNING",
            metadata=_vm_metadata(),
            human_readable_summary="vm-123 is RUNNING.",
            queried_at=datetime.now(timezone.utc),
        )
        assert isinstance(output.metadata, VMMetadata)
        assert output.metadata.machine_type == "e2-standard-4"

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnquiryFoundOutput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                resource_type=ResourceType.compute_instance,
                resource_name="vm-123",
                metadata=_vm_metadata(),
                human_readable_summary="vm-123 is RUNNING.",
                queried_at=datetime.now(timezone.utc),
            )


@pytest.mark.contract
class TestEnquiryListOutputSchema:
    def test_valid_list_output(self) -> None:
        resources = [
            ResourceSummary(
                resource_name="vm-001",
                resource_type=ResourceType.compute_instance,
                gcp_status="RUNNING",
                zone_or_region="us-central1-a",
                key_metadata="e2-standard-4",
            )
        ]
        output = EnquiryListOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.compute_instance,
            project_id="agentic-infraops",
            resources=resources,
            total_count=1,
            human_readable_summary="Found 1 compute instance(s).",
            queried_at=datetime.now(timezone.utc),
        )
        assert output.status == "listed"
        assert output.query_type == "list"
        assert output.total_count == 1
        assert len(output.resources) == 1

    def test_empty_resources_list_valid(self) -> None:
        output = EnquiryListOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.compute_instance,
            project_id="agentic-infraops",
            resources=[],
            total_count=0,
            human_readable_summary="No compute instances found.",
            queried_at=datetime.now(timezone.utc),
        )
        assert output.total_count == 0
        assert output.resources == []

    def test_resources_default_empty(self) -> None:
        output = EnquiryListOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.vpc_network,
            project_id="agentic-infraops",
            total_count=0,
            human_readable_summary="No VPCs found.",
            queried_at=datetime.now(timezone.utc),
        )
        assert output.resources == []


@pytest.mark.contract
class TestEnquiryNotFoundOutputSchema:
    def test_valid_not_found_output(self) -> None:
        output = EnquiryNotFoundOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            resource_type=ResourceType.compute_instance,
            resource_name="ghost-vm",
            message="No resource named 'ghost-vm' found.",
        )
        assert output.status == "not_found"
        assert output.resource_name == "ghost-vm"
        assert "ghost-vm" in output.message

    def test_missing_resource_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnquiryNotFoundOutput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                resource_type=ResourceType.compute_instance,
                message="Not found.",
            )

    def test_all_resource_types_accepted(self) -> None:
        for rt in ResourceType:
            output = EnquiryNotFoundOutput(
                correlation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                resource_type=rt,
                resource_name="missing-resource",
                message=f"Not found: {rt.value}",
            )
            assert output.resource_type == rt


@pytest.mark.contract
class TestEnquiryAccessDeniedOutputSchema:
    def test_valid_access_denied_output(self) -> None:
        output = EnquiryAccessDeniedOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
        )
        assert output.status == "access_denied"
        assert "permission" in output.message.lower()

    def test_custom_message_accepted(self) -> None:
        output = EnquiryAccessDeniedOutput(
            correlation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            message="Custom denial message.",
        )
        assert output.message == "Custom denial message."

    def test_missing_correlation_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnquiryAccessDeniedOutput(request_id=uuid.uuid4())
