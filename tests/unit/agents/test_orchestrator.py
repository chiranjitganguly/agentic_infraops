import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from contracts.schemas.user_role import DeveloperGuardrails, UserRoleType
from agents.orchestrator.agent import (
    ClassifierClient,
    OrchestratorInput,
    OrchestratorOutput,
    Outcome,
    route,
)
from skills.intent_classification.classifier import (
    ClassificationResult,
    NormalizedEnquiryRequest,
    NormalizedVMRequest,
)


CORRELATION_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
REQUEST_ID = UUID("bbbbbbbb-0000-0000-0000-000000000002")

DEFAULT_GUARDRAILS = DeveloperGuardrails(
    allowed_regions=["us-central1", "us-east1", "europe-west1"],
    allowed_machine_types=["e2-standard-2", "e2-standard-4", "e2-standard-8"],
    allowed_storage_classes=["STANDARD", "NEARLINE"],
)


def make_input(raw_input="Create a VM in us-central1", user_role=UserRoleType.developer):
    return OrchestratorInput(
        correlation_id=CORRELATION_ID,
        request_id=REQUEST_ID,
        raw_input=raw_input,
        channel="web",
        requesting_user="dev@example.com",
        user_role=user_role,
    )


class FakeClassifier(ClassifierClient):
    def __init__(self, *, intent="provision", confidence=0.95, region="us-central1",
                 machine_type="e2-standard-4", resource_name="my-vm",
                 resource_type="compute_instance") -> None:
        self._intent = intent
        self._confidence = confidence
        self._region = region
        self._machine_type = machine_type
        self._resource_name = resource_name
        self._resource_type = resource_type

    async def classify(self, raw_input: str, channel: str):  # type: ignore[override]
        if self._intent == "provision":
            normalized = NormalizedVMRequest(
                resource_name=self._resource_name,
                region=self._region,
                machine_type=self._machine_type,
            )
        elif self._intent == "enquiry":
            normalized = NormalizedEnquiryRequest(
                resource_type=self._resource_type,
                resource_name=self._resource_name,
                query_type="list" if not self._resource_name else "single",
            )
        else:
            normalized = None
        return ClassificationResult(
            intent=self._intent,
            confidence=self._confidence,
            normalized=normalized,
        )


def make_postgres(limit_reached=False):
    client = MagicMock()
    client.increment_daily_usage = AsyncMock(
        return_value={"count": 1, "limit_reached": limit_reached}
    )
    return client


def make_provisioning_agent():
    client = MagicMock()
    client.submit = AsyncMock(return_value={"status": "awaiting_confirmation"})
    return client


def make_enquiry_agent():
    client = MagicMock()
    client.submit = AsyncMock(return_value={"status": "found"})
    return client


# B1: confidence < 0.7 → clarification_needed, nothing downstream called
@pytest.mark.anyio
async def test_low_confidence_returns_clarification_needed():
    classifier = FakeClassifier(confidence=0.5)
    pg = make_postgres()
    provisioning = make_provisioning_agent()
    enquiry = make_enquiry_agent()

    result = await route(
        input=make_input(),
        classifier=classifier,
        guardrails=DEFAULT_GUARDRAILS,
        postgres=pg,
        provisioning_agent=provisioning,
        enquiry_agent=enquiry,
    )

    assert result.outcome == Outcome.clarification_needed
    assert result.confidence == pytest.approx(0.5)
    pg.increment_daily_usage.assert_not_called()
    provisioning.submit.assert_not_called()
    enquiry.submit.assert_not_called()


# B2: provision + developer + allowed params + under limit → routed, agent + postgres called
@pytest.mark.anyio
async def test_provision_intent_routes_to_provisioning_agent():
    classifier = FakeClassifier(
        intent="provision", confidence=0.95,
        region="us-central1", machine_type="e2-standard-4",
    )
    pg = make_postgres(limit_reached=False)
    provisioning = make_provisioning_agent()
    enquiry = make_enquiry_agent()

    result = await route(
        input=make_input(),
        classifier=classifier,
        guardrails=DEFAULT_GUARDRAILS,
        postgres=pg,
        provisioning_agent=provisioning,
        enquiry_agent=enquiry,
    )

    assert result.outcome == Outcome.routed
    assert result.intent == "provision"
    pg.increment_daily_usage.assert_called_once_with(requesting_user="dev@example.com", daily_limit=10)
    provisioning.submit.assert_called_once()
    enquiry.submit.assert_not_called()


# B3: guardrail violation → guardrail_violation outcome, postgres not incremented
@pytest.mark.anyio
async def test_guardrail_violation_blocks_before_incrementing_usage():
    classifier = FakeClassifier(
        intent="provision", confidence=0.92,
        region="asia-southeast1",       # outside allowed regions
        machine_type="n2-standard-96",  # outside allowed machine types
    )
    pg = make_postgres()
    provisioning = make_provisioning_agent()
    enquiry = make_enquiry_agent()

    result = await route(
        input=make_input(),
        classifier=classifier,
        guardrails=DEFAULT_GUARDRAILS,
        postgres=pg,
        provisioning_agent=provisioning,
        enquiry_agent=enquiry,
    )

    assert result.outcome == Outcome.guardrail_violation
    assert result.violations is not None
    violated_fields = {v["field"] for v in result.violations}
    assert violated_fields == {"region", "machine_type"}
    pg.increment_daily_usage.assert_not_called()
    provisioning.submit.assert_not_called()


# B4: daily limit reached → rate_limited, provisioning agent not called
@pytest.mark.anyio
async def test_daily_limit_reached_returns_rate_limited():
    classifier = FakeClassifier(
        intent="provision", confidence=0.95,
        region="us-central1", machine_type="e2-standard-4",
    )
    pg = make_postgres(limit_reached=True)
    provisioning = make_provisioning_agent()
    enquiry = make_enquiry_agent()

    result = await route(
        input=make_input(),
        classifier=classifier,
        guardrails=DEFAULT_GUARDRAILS,
        postgres=pg,
        provisioning_agent=provisioning,
        enquiry_agent=enquiry,
    )

    assert result.outcome == Outcome.rate_limited
    pg.increment_daily_usage.assert_called_once()
    provisioning.submit.assert_not_called()


# B5: enquiry intent → routed to enquiry agent, daily usage not incremented
@pytest.mark.anyio
async def test_enquiry_intent_routes_to_enquiry_agent_without_incrementing_usage():
    classifier = FakeClassifier(intent="enquiry", confidence=0.91)
    pg = make_postgres()
    provisioning = make_provisioning_agent()
    enquiry = make_enquiry_agent()

    result = await route(
        input=make_input(raw_input="What is the status of vm-123?"),
        classifier=classifier,
        guardrails=DEFAULT_GUARDRAILS,
        postgres=pg,
        provisioning_agent=provisioning,
        enquiry_agent=enquiry,
    )

    assert result.outcome == Outcome.routed
    assert result.intent == "enquiry"
    enquiry.submit.assert_called_once()
    provisioning.submit.assert_not_called()
    pg.increment_daily_usage.assert_not_called()
