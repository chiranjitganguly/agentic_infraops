"""T097 — Integration test: concurrent load.

Submits 50 concurrent provisioning requests (mix of VM and bucket) via
the orchestrator's route() function with in-process stubs.

Asserts:
  - All 50 requests receive a job_id (routed outcome)
  - No duplicate job_ids (idempotency proxy)
  - System remains responsive: an enquiry submitted during load
    completes in < 30s

Uses in-process stubs — no external services required.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock

import pytest

from agents.orchestrator.agent import route
from contracts.agents.orchestrator import OrchestratorInput, OrchestratorOutput
from contracts.schemas.infra_request import ChannelType, IntentType
from contracts.schemas.user_role import UserRoleType
from business_logic.intent_classification.classifier import ClassificationResult, NormalizedVMRequest, NormalizedBucketRequest, NormalizedEnquiryRequest

pytestmark = pytest.mark.integration

_TOTAL_REQUESTS = 50
_ENQUIRY_SLA_SECONDS = 30.0


def _vm_input(i: int) -> OrchestratorInput:
    return OrchestratorInput(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        raw_input=f"Create VM worker-load-{i:03d} in us-central1",
        requesting_user=f"loadtest-{i:02d}@example.com",
        channel=ChannelType.web,
        user_role=UserRoleType.platform_engineer,
    )


def _bucket_input(i: int) -> OrchestratorInput:
    return OrchestratorInput(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        raw_input=f"Create bucket load-test-bucket-{i:03d} in us-central1",
        requesting_user=f"loadtest-{i:02d}@example.com",
        channel=ChannelType.web,
        user_role=UserRoleType.platform_engineer,
    )


def _enquiry_input() -> OrchestratorInput:
    return OrchestratorInput(
        correlation_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        raw_input="What is the status of vm-web-01?",
        requesting_user="monitor@example.com",
        channel=ChannelType.web,
        user_role=UserRoleType.platform_engineer,
    )


class _FakePostgres:
    async def increment_daily_usage(self, requesting_user: str, daily_limit: int) -> dict:
        return {"limit_reached": False}

    async def get_user_role(self, user_id: str) -> dict:
        return {}


class _FakeProvisioningAgent:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._seen_ids: set[str] = set()
        self.calls: list[dict] = []

    async def submit(self, **kwargs) -> dict:
        job_id = str(uuid.uuid4())
        async with self._lock:
            self._seen_ids.add(job_id)
            self.calls.append(kwargs)
        await asyncio.sleep(0.001)  # simulate minimal I/O
        return {"job_id": job_id, "status": "queued"}


class _FakeEnquiryAgent:
    async def submit(self, **kwargs) -> dict:
        await asyncio.sleep(0.001)
        return {"resources": [{"name": "vm-web-01", "status": "RUNNING"}]}


class _FixedClassifier:
    def __init__(self, intent: str, normalized) -> None:
        self._intent = intent
        self._normalized = normalized

    async def classify(self, raw_input: str, channel: str) -> ClassificationResult:
        return ClassificationResult(intent=self._intent, confidence=0.95, normalized=self._normalized)


async def _submit_one(
    inp: OrchestratorInput,
    classifier,
    provisioning_agent: _FakeProvisioningAgent,
    enquiry_agent: _FakeEnquiryAgent,
) -> OrchestratorOutput:
    return await route(
        input=inp,
        postgres=_FakePostgres(),
        provisioning_agent=provisioning_agent,
        enquiry_agent=enquiry_agent,
        classifier=classifier,
    )


@pytest.mark.asyncio
async def test_50_concurrent_requests_all_routed() -> None:
    """50 concurrent provision requests all return routed outcome with a job_id."""
    provisioning_agent = _FakeProvisioningAgent()
    enquiry_agent = _FakeEnquiryAgent()

    inputs_and_classifiers = []
    for i in range(_TOTAL_REQUESTS):
        if i % 2 == 0:
            inp = _vm_input(i)
            normalized = NormalizedVMRequest(
                resource_name=f"worker-load-{i:03d}",
                region="us-central1",
                zone="us-central1-a",
                machine_type="e2-standard-2",
            )
        else:
            inp = _bucket_input(i)
            normalized = NormalizedBucketRequest(
                resource_name=f"load-test-bucket-{i:03d}",
                region="us-central1",
                storage_class="STANDARD",
            )
        classifier = _FixedClassifier("provision", normalized)
        inputs_and_classifiers.append((inp, classifier))

    tasks = [
        _submit_one(inp, clf, provisioning_agent, enquiry_agent)
        for inp, clf in inputs_and_classifiers
    ]
    results = await asyncio.gather(*tasks)

    assert len(results) == _TOTAL_REQUESTS, f"Expected {_TOTAL_REQUESTS} results, got {len(results)}"

    for i, result in enumerate(results):
        assert result.outcome.value == "routed", f"Request {i}: expected routed, got {result.outcome}"
        assert result.sub_agent_result is not None, f"Request {i}: no sub_agent_result"
        assert "job_id" in result.sub_agent_result, f"Request {i}: no job_id in result"


@pytest.mark.asyncio
async def test_no_duplicate_job_ids_under_load() -> None:
    """No duplicate job_ids across 50 concurrent provisioning requests."""
    provisioning_agent = _FakeProvisioningAgent()
    enquiry_agent = _FakeEnquiryAgent()

    tasks = []
    for i in range(_TOTAL_REQUESTS):
        inp = _vm_input(i)
        normalized = NormalizedVMRequest(
            resource_name=f"worker-{i:03d}",
            region="us-central1",
            zone="us-central1-a",
            machine_type="e2-standard-2",
        )
        classifier = _FixedClassifier("provision", normalized)
        tasks.append(_submit_one(inp, classifier, provisioning_agent, enquiry_agent))

    results = await asyncio.gather(*tasks)

    job_ids = [r.sub_agent_result["job_id"] for r in results if r.sub_agent_result]
    assert len(job_ids) == len(set(job_ids)), f"Duplicate job_ids found: {len(job_ids) - len(set(job_ids))} duplicates"


@pytest.mark.asyncio
async def test_enquiry_responsive_during_load() -> None:
    """An enquiry request completes within 30s SLA while 50 provisioning requests run concurrently."""
    provisioning_agent = _FakeProvisioningAgent()
    enquiry_agent = _FakeEnquiryAgent()

    provision_tasks = []
    for i in range(_TOTAL_REQUESTS):
        inp = _vm_input(i)
        normalized = NormalizedVMRequest(
            resource_name=f"worker-enq-{i:03d}",
            region="us-central1",
            zone="us-central1-a",
            machine_type="e2-standard-2",
        )
        classifier = _FixedClassifier("provision", normalized)
        provision_tasks.append(_submit_one(inp, classifier, provisioning_agent, enquiry_agent))

    enq_inp = _enquiry_input()
    enq_normalized = NormalizedEnquiryRequest(
        resource_type="compute_instance",
        resource_name="vm-web-01",
        query_type="single",
    )
    enq_classifier = _FixedClassifier("enquiry", enq_normalized)

    start = time.perf_counter()
    all_tasks = provision_tasks + [_submit_one(enq_inp, enq_classifier, provisioning_agent, enquiry_agent)]
    results = await asyncio.gather(*all_tasks)
    elapsed = time.perf_counter() - start

    enquiry_result = results[-1]
    assert enquiry_result.outcome.value == "routed", f"Enquiry not routed: {enquiry_result.outcome}"
    assert elapsed < _ENQUIRY_SLA_SECONDS, f"System not responsive under load: {elapsed:.2f}s >= {_ENQUIRY_SLA_SECONDS}s"
