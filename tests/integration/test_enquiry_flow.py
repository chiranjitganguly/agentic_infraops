"""T075 — Integration test: end-to-end infrastructure status enquiry flow.

Tests:
  1. Single resource found — validates gcp_status, typed metadata, human_readable_summary
  2. Resource not found → not_found status
  3. Access denied (resource_name absent for single query)
  4. List query → resources[] non-empty, total_count correct
  5. Bucket status query → BucketMetadata-shaped response
  6. All responses within 30-second SLA
  7. status_queried audit event emitted on every successful query
  8. Direct GET /api/v1/resources/{type}/{name} endpoint → typed metadata

Uses in-process stubs — no external services required.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from agents.enquiry.agent import handle_enquiry
from contracts.agents.enquiry import (
    BucketMetadata,
    EnquiryFoundOutput,
    EnquiryInput,
    EnquiryListOutput,
    EnquiryNotFoundOutput,
    ResourceSummary,
    VMMetadata,
)
from contracts.schemas.provisioning_job import ResourceType
from contracts.schemas.user_role import UserRoleType

pytestmark = pytest.mark.integration

# ─── Shared fixtures ─────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc)

_FAKE_VM_STATUS = {
    "resource_type": "compute_instance",
    "resource_name": "vm-123",
    "gcp_status": "RUNNING",
    "zone": "us-central1-a",
    "metadata": VMMetadata(
        machine_type="e2-standard-4",
        zone="us-central1-a",
        network="global/networks/default",
        disk_size_gb=50,
        internal_ip="10.128.0.2",
    ),
    "queried_at": _NOW,
}

_FAKE_BUCKET_STATUS = {
    "resource_type": "storage_bucket",
    "resource_name": "my-bucket",
    "gcp_status": "ACTIVE",
    "region": "us-central1",
    "metadata": BucketMetadata(
        storage_class="STANDARD",
        location="US-CENTRAL1",
        location_type="region",
        versioning_enabled=False,
        uniform_bucket_level_access=True,
        public_access_prevention="enforced",
    ),
    "queried_at": _NOW,
}

_FAKE_RESOURCES = [
    ResourceSummary(
        resource_name="vm-001",
        resource_type=ResourceType.compute_instance,
        gcp_status="RUNNING",
        zone_or_region="us-central1-a",
        key_metadata="e2-standard-4",
    ),
    ResourceSummary(
        resource_name="vm-002",
        resource_type=ResourceType.compute_instance,
        gcp_status="TERMINATED",
        zone_or_region="us-east1-b",
        key_metadata="e2-standard-2",
    ),
]


def _make_input(**overrides) -> EnquiryInput:
    base = dict(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        query_type="single",
        resource_type=ResourceType.compute_instance,
        resource_name="vm-123",
        project_id="test-project",
        zone="us-central1-a",
        requesting_user="dev@example.com",
        user_role=UserRoleType.developer,
    )
    base.update(overrides)
    return EnquiryInput(**base)


# ─── Single resource found ────────────────────────────────────────────────────

async def test_single_resource_found_status_and_metadata() -> None:
    """Found resource returns gcp_status, typed VMMetadata fields, non-empty summary."""
    inp = _make_input()

    with (
        patch("agents.enquiry.agent.query_resource_status", return_value=_FAKE_VM_STATUS),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        result = await handle_enquiry(inp)

    assert result["status"] == "found"
    assert result["gcp_status"] == "RUNNING"
    assert result["resource_name"] == "vm-123"
    assert result["human_readable_summary"] != ""
    meta = result.get("metadata", {})
    assert meta.get("machine_type") == "e2-standard-4"
    assert meta.get("zone") == "us-central1-a"
    assert meta.get("disk_size_gb") == 50


async def test_single_resource_found_within_30s_sla() -> None:
    """Single resource query completes within 30-second SLA."""
    inp = _make_input()

    with (
        patch("agents.enquiry.agent.query_resource_status", return_value=_FAKE_VM_STATUS),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        start = time.perf_counter()
        result = await handle_enquiry(inp)
        elapsed = time.perf_counter() - start

    assert elapsed < 30.0, f"SLA exceeded: {elapsed:.2f}s"
    assert result["status"] == "found"


# ─── Resource not found ───────────────────────────────────────────────────────

async def test_resource_not_found_returns_not_found_status() -> None:
    """Missing resource returns not_found with descriptive message."""
    inp = _make_input(resource_name="ghost-vm")
    not_found = {
        "not_found": True,
        "resource_name": "ghost-vm",
        "resource_type": ResourceType.compute_instance,
    }

    with (
        patch("agents.enquiry.agent.query_resource_status", return_value=not_found),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        result = await handle_enquiry(inp)

    assert result["status"] == "not_found"
    assert "ghost-vm" in result["message"]
    assert result.get("resource_name") == "ghost-vm"


# ─── Access denied ────────────────────────────────────────────────────────────

async def test_access_denied_when_resource_name_absent_for_single_query() -> None:
    """Single query with resource_name=None returns access_denied immediately."""
    inp = _make_input(query_type="single", resource_name=None)

    result = await handle_enquiry(inp)

    assert result["status"] == "access_denied"
    assert result.get("message", "") != ""


# ─── List query ───────────────────────────────────────────────────────────────

async def test_list_query_returns_resources_array_and_total_count() -> None:
    """List query returns resources[] non-empty with correct total_count."""
    inp = _make_input(query_type="list", resource_name=None, zone=None)

    with (
        patch("agents.enquiry.agent.list_resources", return_value=_FAKE_RESOURCES),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        result = await handle_enquiry(inp)

    assert result["status"] == "listed"
    assert result["query_type"] == "list"
    assert result["total_count"] == 2
    assert len(result["resources"]) == 2
    assert result["human_readable_summary"] != ""
    names = [r["resource_name"] for r in result["resources"]]
    assert "vm-001" in names
    assert "vm-002" in names


async def test_list_query_empty_returns_zero_count() -> None:
    """List query with no resources returns total_count=0 and empty resources[]."""
    inp = _make_input(query_type="list", resource_name=None, zone=None)

    with (
        patch("agents.enquiry.agent.list_resources", return_value=[]),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        result = await handle_enquiry(inp)

    assert result["status"] == "listed"
    assert result["total_count"] == 0
    assert result["resources"] == []


async def test_list_query_within_30s_sla() -> None:
    """List query completes within 30-second SLA."""
    inp = _make_input(query_type="list", resource_name=None, zone=None)

    with (
        patch("agents.enquiry.agent.list_resources", return_value=_FAKE_RESOURCES),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        start = time.perf_counter()
        result = await handle_enquiry(inp)
        elapsed = time.perf_counter() - start

    assert elapsed < 30.0, f"SLA exceeded: {elapsed:.2f}s"
    assert result["status"] == "listed"


# ─── Bucket status ────────────────────────────────────────────────────────────

async def test_bucket_status_returns_bucket_metadata() -> None:
    """Bucket query returns BucketMetadata-shaped metadata and ACTIVE status."""
    inp = _make_input(
        resource_type=ResourceType.storage_bucket,
        resource_name="my-bucket",
        zone=None,
        region="us-central1",
    )

    with (
        patch("agents.enquiry.agent.query_resource_status", return_value=_FAKE_BUCKET_STATUS),
        patch("agents.enquiry.agent._emit_audit_event", new_callable=AsyncMock),
    ):
        result = await handle_enquiry(inp)

    assert result["status"] == "found"
    assert result["gcp_status"] == "ACTIVE"
    meta = result.get("metadata", {})
    assert meta.get("storage_class") == "STANDARD"
    assert meta.get("location") == "US-CENTRAL1"
    assert "versioning" in result["human_readable_summary"].lower()


# ─── Audit event emission ─────────────────────────────────────────────────────

async def test_status_queried_audit_event_emitted_for_found() -> None:
    """_emit_audit_event is called with 'found' outcome after successful query."""
    inp = _make_input()
    mock_audit = AsyncMock()

    with (
        patch("agents.enquiry.agent.query_resource_status", return_value=_FAKE_VM_STATUS),
        patch("agents.enquiry.agent._emit_audit_event", mock_audit),
    ):
        await handle_enquiry(inp)

    mock_audit.assert_called_once()
    _inp_arg, outcome_arg = mock_audit.call_args[0]
    assert outcome_arg == "found"


async def test_status_queried_audit_event_emitted_for_listed() -> None:
    """_emit_audit_event is called with 'listed' outcome after list query."""
    inp = _make_input(query_type="list", resource_name=None, zone=None)
    mock_audit = AsyncMock()

    with (
        patch("agents.enquiry.agent.list_resources", return_value=_FAKE_RESOURCES),
        patch("agents.enquiry.agent._emit_audit_event", mock_audit),
    ):
        await handle_enquiry(inp)

    mock_audit.assert_called_once()
    _inp_arg, outcome_arg = mock_audit.call_args[0]
    assert outcome_arg == "listed"


async def test_status_queried_audit_event_emitted_for_not_found() -> None:
    """_emit_audit_event is called with 'not_found' outcome when resource is missing."""
    inp = _make_input(resource_name="missing-vm")
    not_found = {"not_found": True, "resource_name": "missing-vm", "resource_type": ResourceType.compute_instance}
    mock_audit = AsyncMock()

    with (
        patch("agents.enquiry.agent.query_resource_status", return_value=not_found),
        patch("agents.enquiry.agent._emit_audit_event", mock_audit),
    ):
        await handle_enquiry(inp)

    mock_audit.assert_called_once()
    _inp_arg, outcome_arg = mock_audit.call_args[0]
    assert outcome_arg == "not_found"


# ─── Direct REST endpoint ─────────────────────────────────────────────────────

async def test_direct_rest_endpoint_returns_typed_metadata() -> None:
    """GET /api/v1/resources/{resource_type}/{resource_name} returns typed metadata."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from web.backend.routers.resources import router as resources_router

    test_app = FastAPI()
    test_app.include_router(resources_router, prefix="/api/v1")

    with patch(
        "web.backend.routers.resources.query_resource_status",
        return_value=_FAKE_VM_STATUS,
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/resources/compute_instance/vm-123",
                params={"project_id": "test-project", "zone": "us-central1-a"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["resource_type"] == "compute_instance"
    assert data["gcp_status"] == "RUNNING"
    assert data["resource_name"] == "vm-123"
    assert data["human_readable_summary"] != ""
    meta = data.get("metadata", {})
    assert meta.get("machine_type") == "e2-standard-4"


async def test_direct_rest_endpoint_not_found_returns_404() -> None:
    """GET /api/v1/resources/{type}/{name} returns 404 when resource does not exist."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from web.backend.routers.resources import router as resources_router

    test_app = FastAPI()
    test_app.include_router(resources_router, prefix="/api/v1")

    not_found = {"not_found": True, "resource_name": "no-vm", "resource_type": ResourceType.compute_instance}

    with patch(
        "web.backend.routers.resources.query_resource_status",
        return_value=not_found,
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/resources/compute_instance/no-vm",
                params={"project_id": "test-project", "zone": "us-central1-a"},
            )

    assert response.status_code == 404


async def test_direct_rest_list_endpoint_returns_resource_array() -> None:
    """GET /api/v1/resources?resource_type=compute_instance returns ResourceSummary[]."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from web.backend.routers.resources import router as resources_router

    test_app = FastAPI()
    test_app.include_router(resources_router, prefix="/api/v1")

    with patch(
        "web.backend.routers.resources.list_resources",
        return_value=_FAKE_RESOURCES,
    ):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/resources",
                params={"resource_type": "compute_instance", "project_id": "test-project"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["resource_type"] == "compute_instance"
    assert data["total_count"] == 2
    assert len(data["resources"]) == 2
    assert data["resources"][0]["resource_name"] == "vm-001"


async def test_direct_rest_endpoint_invalid_resource_type_returns_400() -> None:
    """GET /api/v1/resources with invalid resource_type returns 400."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from web.backend.routers.resources import router as resources_router

    test_app = FastAPI()
    test_app.include_router(resources_router, prefix="/api/v1")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/resources",
            params={"resource_type": "invalid_type", "project_id": "test-project"},
        )

    assert response.status_code == 400
