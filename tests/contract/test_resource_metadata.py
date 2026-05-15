"""T068a — Contract tests for typed resource metadata models.

Validates VMMetadata, BucketMetadata, VPCMetadata, and ResourceSummary
against sample GCP API response fixture data.
No external services required.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.agents.enquiry import (
    BucketMetadata,
    ResourceSummary,
    SubnetSummary,
    VMMetadata,
    VPCMetadata,
)
from contracts.schemas.provisioning_job import ResourceType


# ─── Sample GCP API response fixtures ────────────────────────────────────────

_VM_GCP_FIXTURE = {
    "machine_type": "e2-standard-4",
    "zone": "us-central1-a",
    "network": "global/networks/default",
    "subnetwork": "regions/us-central1/subnetworks/default",
    "internal_ip": "10.128.0.2",
    "external_ip": "34.123.0.5",
    "disk_size_gb": 50,
    "creation_timestamp": "2026-01-15T10:00:00+00:00",
    "labels": {"env": "dev", "team": "infra"},
}

_BUCKET_GCP_FIXTURE = {
    "storage_class": "STANDARD",
    "location": "US-CENTRAL1",
    "location_type": "region",
    "versioning_enabled": False,
    "uniform_bucket_level_access": True,
    "public_access_prevention": "enforced",
    "creation_time": "2026-01-10T08:30:00+00:00",
    "labels": {"team": "data"},
}

_VPC_GCP_FIXTURE = {
    "auto_create_subnetworks": False,
    "routing_mode": "REGIONAL",
    "subnet_count": 2,
    "subnets": [
        {
            "name": "subnet-us",
            "region": "us-central1",
            "cidr": "10.0.0.0/24",
            "private_google_access": True,
        },
        {
            "name": "subnet-eu",
            "region": "europe-west1",
            "cidr": "10.0.1.0/24",
            "private_google_access": False,
        },
    ],
    "creation_timestamp": "2026-01-01T12:00:00+00:00",
}


@pytest.mark.contract
class TestVMMetadata:
    def test_valid_from_gcp_response(self) -> None:
        m = VMMetadata(**_VM_GCP_FIXTURE)
        assert m.machine_type == "e2-standard-4"
        assert m.zone == "us-central1-a"
        assert m.internal_ip == "10.128.0.2"
        assert m.external_ip == "34.123.0.5"
        assert m.disk_size_gb == 50
        assert m.labels == {"env": "dev", "team": "infra"}
        assert m.creation_timestamp is not None

    def test_optional_fields_default_none(self) -> None:
        m = VMMetadata(machine_type="e2-micro", zone="us-central1-a", network="default", disk_size_gb=10)
        assert m.subnetwork is None
        assert m.internal_ip is None
        assert m.external_ip is None
        assert m.creation_timestamp is None

    def test_labels_default_empty_dict(self) -> None:
        m = VMMetadata(machine_type="e2-micro", zone="us-central1-a", network="default", disk_size_gb=10)
        assert m.labels == {}

    def test_missing_machine_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            VMMetadata(zone="us-central1-a", network="default", disk_size_gb=10)

    def test_missing_zone_raises(self) -> None:
        with pytest.raises(ValidationError):
            VMMetadata(machine_type="e2-standard-4", network="default", disk_size_gb=10)

    def test_missing_disk_size_raises(self) -> None:
        with pytest.raises(ValidationError):
            VMMetadata(machine_type="e2-standard-4", zone="us-central1-a", network="default")

    def test_serialises_to_json(self) -> None:
        m = VMMetadata(**_VM_GCP_FIXTURE)
        dumped = m.model_dump(mode="json")
        assert dumped["machine_type"] == "e2-standard-4"
        assert isinstance(dumped["labels"], dict)


@pytest.mark.contract
class TestBucketMetadata:
    def test_valid_from_gcp_response(self) -> None:
        m = BucketMetadata(**_BUCKET_GCP_FIXTURE)
        assert m.storage_class == "STANDARD"
        assert m.location == "US-CENTRAL1"
        assert m.location_type == "region"
        assert m.versioning_enabled is False
        assert m.uniform_bucket_level_access is True
        assert m.public_access_prevention == "enforced"
        assert m.creation_time is not None

    def test_optional_fields_default(self) -> None:
        m = BucketMetadata(
            storage_class="NEARLINE",
            location="US",
            location_type="multi-region",
            versioning_enabled=True,
            uniform_bucket_level_access=False,
            public_access_prevention="inherited",
        )
        assert m.labels == {}
        assert m.creation_time is None

    def test_versioning_enabled_true(self) -> None:
        m = BucketMetadata(
            storage_class="STANDARD",
            location="US-CENTRAL1",
            location_type="region",
            versioning_enabled=True,
            uniform_bucket_level_access=True,
            public_access_prevention="enforced",
        )
        assert m.versioning_enabled is True

    def test_missing_storage_class_raises(self) -> None:
        with pytest.raises(ValidationError):
            BucketMetadata(
                location="US-CENTRAL1",
                location_type="region",
                versioning_enabled=False,
                uniform_bucket_level_access=True,
                public_access_prevention="enforced",
            )

    def test_serialises_to_json(self) -> None:
        m = BucketMetadata(**_BUCKET_GCP_FIXTURE)
        dumped = m.model_dump(mode="json")
        assert dumped["storage_class"] == "STANDARD"
        assert isinstance(dumped["labels"], dict)


@pytest.mark.contract
class TestVPCMetadata:
    def test_valid_from_gcp_response(self) -> None:
        m = VPCMetadata(**_VPC_GCP_FIXTURE)
        assert m.routing_mode == "REGIONAL"
        assert m.auto_create_subnetworks is False
        assert m.subnet_count == 2
        assert len(m.subnets) == 2
        assert m.subnets[0].name == "subnet-us"
        assert m.subnets[0].private_google_access is True
        assert m.subnets[1].name == "subnet-eu"
        assert m.subnets[1].cidr == "10.0.1.0/24"

    def test_subnets_default_empty(self) -> None:
        m = VPCMetadata(auto_create_subnetworks=True, routing_mode="GLOBAL", subnet_count=0)
        assert m.subnets == []
        assert m.creation_timestamp is None

    def test_missing_routing_mode_raises(self) -> None:
        with pytest.raises(ValidationError):
            VPCMetadata(auto_create_subnetworks=False, subnet_count=0)

    def test_missing_auto_create_raises(self) -> None:
        with pytest.raises(ValidationError):
            VPCMetadata(routing_mode="REGIONAL", subnet_count=0)

    def test_serialises_to_json(self) -> None:
        m = VPCMetadata(**_VPC_GCP_FIXTURE)
        dumped = m.model_dump(mode="json")
        assert dumped["routing_mode"] == "REGIONAL"
        assert isinstance(dumped["subnets"], list)
        assert dumped["subnets"][0]["name"] == "subnet-us"


@pytest.mark.contract
class TestSubnetSummary:
    def test_valid_subnet(self) -> None:
        s = SubnetSummary(
            name="my-subnet",
            region="us-central1",
            cidr="192.168.0.0/24",
            private_google_access=True,
        )
        assert s.name == "my-subnet"
        assert s.region == "us-central1"
        assert s.cidr == "192.168.0.0/24"
        assert s.private_google_access is True

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            SubnetSummary(region="us-central1", cidr="10.0.0.0/24", private_google_access=False)


@pytest.mark.contract
class TestResourceSummary:
    def test_valid_vm_summary(self) -> None:
        s = ResourceSummary(
            resource_name="vm-001",
            resource_type=ResourceType.compute_instance,
            gcp_status="RUNNING",
            zone_or_region="us-central1-a",
            key_metadata="e2-standard-4",
        )
        assert s.resource_type == ResourceType.compute_instance
        assert s.gcp_status == "RUNNING"
        assert s.creation_timestamp is None

    def test_valid_bucket_summary_with_timestamp(self) -> None:
        s = ResourceSummary(
            resource_name="my-bucket",
            resource_type=ResourceType.storage_bucket,
            gcp_status="ACTIVE",
            zone_or_region="us-central1",
            key_metadata="STANDARD",
            creation_timestamp=datetime.now(timezone.utc),
        )
        assert s.resource_type == ResourceType.storage_bucket
        assert s.creation_timestamp is not None

    def test_vpc_summary_zone_or_region_optional(self) -> None:
        s = ResourceSummary(
            resource_name="my-vpc",
            resource_type=ResourceType.vpc_network,
            gcp_status="ACTIVE",
            key_metadata="REGIONAL",
        )
        assert s.zone_or_region is None

    def test_all_resource_types_valid(self) -> None:
        for rt in ResourceType:
            s = ResourceSummary(
                resource_name=f"res-{rt.value}",
                resource_type=rt,
                gcp_status="ACTIVE",
                key_metadata="metadata",
            )
            assert s.resource_type == rt

    def test_missing_resource_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResourceSummary(
                resource_type=ResourceType.compute_instance,
                gcp_status="RUNNING",
                key_metadata="e2-standard-4",
            )

    def test_serialises_to_json(self) -> None:
        s = ResourceSummary(
            resource_name="vm-001",
            resource_type=ResourceType.compute_instance,
            gcp_status="RUNNING",
            zone_or_region="us-central1-a",
            key_metadata="e2-standard-4",
        )
        dumped = s.model_dump(mode="json")
        assert dumped["resource_type"] == "compute_instance"
        assert dumped["gcp_status"] == "RUNNING"
