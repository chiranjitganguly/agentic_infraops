from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol
from uuid import UUID

from contracts.agents.provisioning import VMParameters
from contracts.schemas.user_role import DeveloperGuardrails, UserRoleType
from skills.gcp_compute.guardrails import validate_developer_guardrails


class Outcome(str, Enum):
    routed = "routed"
    clarification_needed = "clarification_needed"
    guardrail_violation = "guardrail_violation"
    rate_limited = "rate_limited"
    rejected = "rejected"


@dataclass
class OrchestratorInput:
    correlation_id: UUID
    request_id: UUID
    raw_input: str
    channel: str
    requesting_user: str
    user_role: UserRoleType
    email_thread_id: str | None = None


@dataclass
class OrchestratorOutput:
    correlation_id: UUID
    request_id: UUID
    outcome: Outcome
    intent: str | None = None
    confidence: float | None = None
    clarification_question: str | None = None
    rejection_reason: str | None = None
    sub_agent_result: dict | None = None
    violations: list = field(default_factory=list)


class ClassifierClient(Protocol):
    async def classify(self, raw_input: str, channel: str): ...


class PostgresClient(Protocol):
    async def increment_daily_usage(self, requesting_user: str) -> dict: ...


class ProvisioningAgentClient(Protocol):
    async def submit(self, **kwargs) -> dict: ...


class EnquiryAgentClient(Protocol):
    async def submit(self, **kwargs) -> dict: ...


def _output(
    input: OrchestratorInput,
    outcome: Outcome,
    classification,
    **kwargs,
) -> OrchestratorOutput:
    return OrchestratorOutput(
        correlation_id=input.correlation_id,
        request_id=input.request_id,
        outcome=outcome,
        intent=classification.intent,
        confidence=classification.confidence,
        **kwargs,
    )


async def route(
    input: OrchestratorInput,
    classifier: ClassifierClient,
    guardrails: DeveloperGuardrails,
    postgres: PostgresClient,
    provisioning_agent: ProvisioningAgentClient,
    enquiry_agent: EnquiryAgentClient,
) -> OrchestratorOutput:
    classification = await classifier.classify(input.raw_input, input.channel)

    if classification.confidence < 0.7:
        return _output(input, Outcome.clarification_needed, classification)

    if classification.intent == "provision" and input.user_role == UserRoleType.developer:
        guardrail_result = validate_developer_guardrails(
            params=VMParameters(machine_type=classification.machine_type),
            region=classification.region,
            user_role=input.user_role,
            guardrails=guardrails,
        )
        if not guardrail_result.passed:
            return _output(input, Outcome.guardrail_violation, classification,
                           violations=guardrail_result.violations)

        usage = await postgres.increment_daily_usage(requesting_user=input.requesting_user)
        if usage["limit_reached"]:
            return _output(input, Outcome.rate_limited, classification)

        sub_result = await provisioning_agent.submit(
            correlation_id=input.correlation_id,
            request_id=input.request_id,
            classification=classification,
            requesting_user=input.requesting_user,
            user_role=input.user_role,
        )
        return _output(input, Outcome.routed, classification, sub_agent_result=sub_result)

    if classification.intent == "enquiry":
        sub_result = await enquiry_agent.submit(
            correlation_id=input.correlation_id,
            request_id=input.request_id,
            classification=classification,
            requesting_user=input.requesting_user,
            user_role=input.user_role,
        )
        return _output(input, Outcome.routed, classification, sub_agent_result=sub_result)

    return _output(input, Outcome.routed, classification)
