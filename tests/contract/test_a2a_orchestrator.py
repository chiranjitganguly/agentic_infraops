"""T035 — Contract tests for Orchestrator Agent A2A input/output schemas.

Validates OrchestratorInput, OrchestratorOutput, and Outcome enum values.
No external services required.
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from contracts.agents.orchestrator import (
    Outcome,
    OrchestratorInput,
    OrchestratorOutput,
)
from contracts.schemas.infra_request import ChannelType, IntentType
from contracts.schemas.user_role import UserRoleType


def _valid_input(**overrides) -> dict:  # type: ignore[no-untyped-def]
    base = {
        "correlation_id": uuid.uuid4(),
        "request_id": uuid.uuid4(),
        "raw_input": "Create a VM with 4 CPUs in us-central1",
        "channel": ChannelType.web,
        "requesting_user": "dev@example.com",
        "user_role": UserRoleType.developer,
    }
    base.update(overrides)
    return base


def _valid_output(outcome: Outcome = Outcome.routed, **overrides) -> dict:  # type: ignore[no-untyped-def]
    base = {
        "correlation_id": uuid.uuid4(),
        "request_id": uuid.uuid4(),
        "outcome": outcome,
    }
    base.update(overrides)
    return base


@pytest.mark.contract
class TestOrchestratorInputSchema:
    def test_valid_web_channel_input(self) -> None:
        inp = OrchestratorInput(**_valid_input())
        assert inp.channel == ChannelType.web
        assert inp.email_thread_id is None

    def test_valid_email_channel_with_thread_id(self) -> None:
        inp = OrchestratorInput(**_valid_input(channel=ChannelType.email, email_thread_id="thread-abc"))
        assert inp.email_thread_id == "thread-abc"

    def test_both_user_roles_accepted(self) -> None:
        for role in UserRoleType:
            inp = OrchestratorInput(**_valid_input(user_role=role))
            assert inp.user_role == role

    def test_empty_raw_input_raises(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorInput(**_valid_input(raw_input=""))

    def test_empty_requesting_user_raises(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorInput(**_valid_input(requesting_user=""))

    def test_chatbot_channel_raises(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorInput(**_valid_input(channel="chatbot"))  # type: ignore[arg-type]

    def test_missing_correlation_id_raises(self) -> None:
        payload = _valid_input()
        del payload["correlation_id"]
        with pytest.raises(ValidationError):
            OrchestratorInput(**payload)

    def test_missing_request_id_raises(self) -> None:
        payload = _valid_input()
        del payload["request_id"]
        with pytest.raises(ValidationError):
            OrchestratorInput(**payload)


@pytest.mark.contract
class TestOrchestratorOutputSchema:
    def test_routed_outcome_with_sub_agent_result(self) -> None:
        output = OrchestratorOutput(
            **_valid_output(
                outcome=Outcome.routed,
                intent=IntentType.provision,
                confidence=0.95,
                sub_agent_result={"job_id": str(uuid.uuid4()), "status": "awaiting_confirmation"},
            )
        )
        assert output.outcome == Outcome.routed
        assert output.sub_agent_result is not None

    def test_clarification_needed_with_question(self) -> None:
        output = OrchestratorOutput(
            **_valid_output(
                outcome=Outcome.clarification_needed,
                clarification_question="Did you mean a VM or a storage bucket?",
                confidence=0.45,
            )
        )
        assert output.clarification_question is not None

    def test_guardrail_violation_outcome(self) -> None:
        output = OrchestratorOutput(**_valid_output(outcome=Outcome.guardrail_violation))
        assert output.outcome == Outcome.guardrail_violation

    def test_confidence_must_be_in_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorOutput(**_valid_output(confidence=1.01))

    def test_confidence_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorOutput(**_valid_output(confidence=-0.01))

    def test_confidence_at_boundaries_accepted(self) -> None:
        low = OrchestratorOutput(**_valid_output(confidence=0.0))
        high = OrchestratorOutput(**_valid_output(confidence=1.0))
        assert low.confidence == 0.0
        assert high.confidence == 1.0

    def test_optional_fields_default_to_none(self) -> None:
        output = OrchestratorOutput(**_valid_output())
        assert output.intent is None
        assert output.confidence is None
        assert output.clarification_question is None
        assert output.rejection_reason is None
        assert output.sub_agent_result is None

    def test_missing_outcome_raises(self) -> None:
        payload = _valid_output()
        del payload["outcome"]
        with pytest.raises(ValidationError):
            OrchestratorOutput(**payload)


@pytest.mark.contract
class TestOutcomeEnum:
    def test_all_expected_outcome_values_present(self) -> None:
        values = {o.value for o in Outcome}
        expected = {
            "routed",
            "clarification_needed",
            "rejected",
            "rate_limited",
            "guardrail_violation",
            "expired",
        }
        assert expected.issubset(values), f"Missing outcomes: {expected - values}"

    def test_intent_type_values(self) -> None:
        values = {i.value for i in IntentType}
        assert "provision" in values
        assert "enquiry" in values
        assert "faq" in values

    def test_channel_type_excludes_chatbot(self) -> None:
        assert "chatbot" not in {c.value for c in ChannelType}
