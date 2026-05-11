"""T045 — Orchestrator Agent: Google ADK-native implementation.

Uses google-adk BaseAgent with Runner + InMemorySessionService.
Exposes root_agent for ADK AgentLoader discovery.

Served via ADK's get_fast_api_app (a2a=True) in __main__.

On each invocation (user message = JSON-serialised OrchestratorInput):
1. Classifies intent via intent_classification skill
2. confidence < 0.7 → clarification_needed (web only; email → rejected)
3. provision + developer → validate guardrails
4. guardrail violation → guardrail_violation outcome
5. Checks daily usage limit via postgres-mcp
6. Routes to Provisioning / Enquiry / FAQ agent via A2A HTTP
7. Yields a single Event whose content.parts[0].text = JSON OrchestratorOutput
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, AsyncGenerator, Protocol

import httpx
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types as genai_types

from agentic_infraops.agents.orchestrator.clarification import (
    IntentCandidate,
    build_clarification_question,
)
from agentic_infraops.contracts.agents.orchestrator import (
    Outcome,
    OrchestratorInput,
    OrchestratorOutput,
)
from agentic_infraops.contracts.schemas.infra_request import ChannelType, IntentType
from agentic_infraops.contracts.schemas.user_role import DeveloperGuardrails, UserRoleType
from agentic_infraops.contracts.shared.correlation import (
    inject_correlation_headers,
    new_correlation_context,
    set_correlation_context,
)
from agentic_infraops.contracts.shared.logging import configure_logging, get_logger
from agentic_infraops.contracts.shared.metrics import start_metrics_server
from agentic_infraops.skills.gcp_compute.guardrails import (
    validate_developer_guardrails,
    validate_vpc_guardrail,
)
from agentic_infraops.skills.intent_classification.classifier import (
    ClassificationResult,
    classify,
)

configure_logging(service_name="orchestrator-agent")
logger = get_logger("orchestrator-agent")


class PostgresClient(Protocol):
    async def increment_daily_usage(self, requesting_user: str) -> dict: ...
    async def get_user_role(self, user_id: str) -> dict: ...


class SubAgentClient(Protocol):
    async def submit(self, **kwargs: Any) -> dict: ...


def _default_guardrails() -> DeveloperGuardrails:
    return DeveloperGuardrails(
        allowed_regions=os.environ.get(
            "ALLOWED_REGIONS", "us-central1,us-east1,europe-west1"
        ).split(","),
        allowed_machine_types=os.environ.get(
            "ALLOWED_MACHINE_TYPES", "e2-standard-2,e2-standard-4,e2-standard-8"
        ).split(","),
        allowed_storage_classes=os.environ.get(
            "ALLOWED_STORAGE_CLASSES", "STANDARD,NEARLINE"
        ).split(","),
        daily_provisioning_limit=int(os.environ.get("DEVELOPER_DAILY_LIMIT", "10")),
    )


async def _call_sub_agent(agent_url: str, task_data: dict[str, Any]) -> dict[str, Any]:
    """Send an A2A task to a sub-agent and return the artifact data."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {"Content-Type": "application/json"}
        inject_correlation_headers(headers)
        response = await client.post(
            f"{agent_url}/tasks",
            json=task_data,
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()
        artifacts = result.get("artifacts", [])
        if artifacts:
            parts = artifacts[0].get("parts", [])
            if parts:
                return parts[0].get("data", {})
    return result


async def route(
    inp: OrchestratorInput,
    postgres: PostgresClient,
    provisioning_agent: SubAgentClient,
    enquiry_agent: SubAgentClient,
    guardrails: DeveloperGuardrails | None = None,
) -> OrchestratorOutput:
    """Core orchestrator routing logic (injectable for testing)."""
    if guardrails is None:
        guardrails = _default_guardrails()

    classification: ClassificationResult = await classify(inp.raw_input, inp.channel)

    if classification.confidence < 0.7:
        if inp.channel == ChannelType.email:
            return OrchestratorOutput(
                correlation_id=inp.correlation_id,
                request_id=inp.request_id,
                outcome=Outcome.rejected,
                intent=IntentType(classification.intent) if classification.intent in IntentType._value2member_map_ else None,
                confidence=classification.confidence,
                rejection_reason=(
                    "I couldn't understand your request. Please send a clearer message. "
                    "Examples: 'Check the status of vm-123' or "
                    "'Create a VM with 4 CPUs in us-central1'."
                ),
            )

        question = build_clarification_question([
            IntentCandidate(intent=classification.intent, confidence=classification.confidence),
        ])
        return OrchestratorOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            outcome=Outcome.clarification_needed,
            intent=IntentType(classification.intent) if classification.intent in IntentType._value2member_map_ else None,
            confidence=classification.confidence,
            clarification_question=question,
        )

    # VPC provisioning is blocked for developers
    if (
        classification.intent == "provision"
        and classification.resource_type == "vpc_network"
        and inp.user_role == UserRoleType.developer
    ):
        validate_vpc_guardrail(inp.user_role)
        return OrchestratorOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            outcome=Outcome.guardrail_violation,
            intent=IntentType.provision,
            confidence=classification.confidence,
        )

    # Validate developer guardrails for compute_instance provisioning
    if (
        classification.intent == "provision"
        and classification.resource_type == "compute_instance"
        and inp.user_role == UserRoleType.developer
    ):
        from agentic_infraops.contracts.agents.provisioning import VMParameters

        vm_params = VMParameters(machine_type=classification.machine_type or "e2-standard-4")
        guardrail_result = validate_developer_guardrails(
            params=vm_params,
            region=classification.region or "",
            user_role=inp.user_role,
            guardrails=guardrails,
        )
        if not guardrail_result.passed:
            return OrchestratorOutput(
                correlation_id=inp.correlation_id,
                request_id=inp.request_id,
                outcome=Outcome.guardrail_violation,
                intent=IntentType.provision,
                confidence=classification.confidence,
            )

    # Daily rate limit check (developers only)
    if classification.intent == "provision" and inp.user_role == UserRoleType.developer:
        usage = await postgres.increment_daily_usage(requesting_user=inp.requesting_user)
        if usage.get("limit_reached"):
            return OrchestratorOutput(
                correlation_id=inp.correlation_id,
                request_id=inp.request_id,
                outcome=Outcome.rate_limited,
                intent=IntentType.provision,
                confidence=classification.confidence,
            )

    # Route to sub-agent
    if classification.intent == "provision":
        sub_result = await provisioning_agent.submit(
            correlation_id=str(inp.correlation_id),
            request_id=str(inp.request_id),
            classification=classification,
            requesting_user=inp.requesting_user,
            user_role=inp.user_role,
        )
    elif classification.intent == "enquiry":
        sub_result = await enquiry_agent.submit(
            correlation_id=str(inp.correlation_id),
            request_id=str(inp.request_id),
            classification=classification,
            requesting_user=inp.requesting_user,
            user_role=inp.user_role,
        )
    else:
        sub_result = {}

    return OrchestratorOutput(
        correlation_id=inp.correlation_id,
        request_id=inp.request_id,
        outcome=Outcome.routed,
        intent=IntentType(classification.intent) if classification.intent in IntentType._value2member_map_ else None,
        confidence=classification.confidence,
        sub_agent_result=sub_result,
    )


# ─── ADK Agent ──────────────────────────────────────────────────────────────

class OrchestratorAgent(BaseAgent):
    """ADK BaseAgent implementing orchestrator routing logic.

    Input: user message parts[0].text = JSON-serialised OrchestratorInput
    Output: single Event with parts[0].text = JSON-serialised OrchestratorOutput
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Extract JSON input from the user message
        user_text = ""
        if ctx.user_content and ctx.user_content.parts:
            user_text = ctx.user_content.parts[0].text or ""

        try:
            task_data = json.loads(user_text)
            inp = OrchestratorInput(**task_data)
        except Exception as exc:
            error_out = {"error": f"Invalid input: {exc}"}
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=json.dumps(error_out))],
                ),
            )
            return

        # Wire up clients
        from agentic_infraops.mcp_servers.postgres.server import increment_daily_usage

        class _PostgresClient:
            async def increment_daily_usage(self, requesting_user: str) -> dict:
                return await increment_daily_usage(requesting_user)

            async def get_user_role(self, user_id: str) -> dict:
                return {}

        provisioning_url = os.environ.get(
            "PROVISIONING_AGENT_URL", "http://provisioning-agent:8002"
        )
        enquiry_url = os.environ.get("ENQUIRY_AGENT_URL", "http://enquiry-agent:8003")

        class _A2AClient:
            def __init__(self, url: str) -> None:
                self._url = url

            async def submit(self, **kwargs: Any) -> dict:
                return await _call_sub_agent(
                    self._url,
                    {
                        "id": str(uuid.uuid4()),
                        "message": {
                            "role": "user",
                            "parts": [{"type": "data", "data": kwargs}],
                        },
                    },
                )

        # Set correlation context
        ctx_corr = new_correlation_context()
        set_correlation_context(ctx_corr)

        output = await route(
            inp=inp,
            postgres=_PostgresClient(),
            provisioning_agent=_A2AClient(provisioning_url),
            enquiry_agent=_A2AClient(enquiry_url),
        )

        logger.info(
            "orchestrator_routed",
            outcome=output.outcome.value,
            intent=output.intent.value if output.intent else None,
        )

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=output.model_dump_json())],
            ),
        )


# ADK AgentLoader discovers 'root_agent' in this module
root_agent = OrchestratorAgent(
    name="orchestrator_agent",
    description=(
        "Classifies natural language infrastructure requests, enforces guardrails and "
        "rate limits, and routes to the appropriate sub-agent."
    ),
)


# ─── Standalone HTTP server (backwards-compatible A2A endpoint) ──────────────

if __name__ == "__main__":
    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get("PORT", "8001"))
    start_metrics_server(port=9001)

    app = get_fast_api_app(
        agents_dir=agents_dir,
        web=False,
        a2a=True,
        host="0.0.0.0",
        port=port,
        allow_origins=["*"],
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
