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

import dataclasses
import json
import os
import uuid
from typing import Any, AsyncGenerator, Protocol

import httpx
from google.adk.agents import BaseAgent
from mcp_servers.postgres.server import increment_daily_usage as _pg_increment_daily_usage
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types as genai_types

from agents.orchestrator.clarification import (
    IntentCandidate,
    build_clarification_question,
)
from contracts.agents.orchestrator import (
    Outcome,
    OrchestratorInput,
    OrchestratorOutput,
)
from contracts.schemas.infra_request import ChannelType, IntentType
from contracts.schemas.user_role import DeveloperGuardrails, UserRoleType
from contracts.shared.correlation import (
    CorrelationContext,
    inject_correlation_headers,
    set_correlation_context,
)
from contracts.shared.logging import configure_logging, get_logger
from contracts.shared.metrics import start_metrics_server
from business_logic.gcp_compute.guardrails import validate_provisioning_guardrails
from business_logic.intent_classification.classifier import (
    ClassificationResult,
    NormalizedBucketRequest,
    NormalizedEnquiryRequest,
    NormalizedFAQRequest,
    NormalizedVMRequest,
    NormalizedVPCRequest,
    classify,
)

configure_logging(service_name="orchestrator-agent")
logger = get_logger("orchestrator-agent")

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")


class PostgresClient(Protocol):
    async def increment_daily_usage(self, requesting_user: str, daily_limit: int) -> dict: ...
    async def get_user_role(self, user_id: str) -> dict: ...


class ClassifierClient(Protocol):
    async def classify(self, raw_input: str, channel: str) -> ClassificationResult: ...


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


def _app_name_from_url(agent_url: str) -> str:
    """Derive ADK app name from service URL hostname (e.g. http://provisioning-agent:8002 → 'provisioning')."""
    from urllib.parse import urlparse
    host = urlparse(agent_url).hostname or ""
    return host.replace("-agent", "").replace("-", "_")


async def _call_sub_agent(agent_url: str, task_data: dict[str, Any]) -> dict[str, Any]:
    """Call an ADK sub-agent via /run and return the parsed output."""
    app_name = _app_name_from_url(agent_url)
    user_id = task_data.get("message", {}).get("role", "orchestrator")
    session_id = str(uuid.uuid4())
    payload = task_data.get("message", {}).get("parts", [{}])[0].get("data", task_data)

    headers: dict[str, str] = {}
    inject_correlation_headers(headers)

    async with httpx.AsyncClient(timeout=60.0) as client:
        await client.post(
            f"{agent_url}/apps/{app_name}/users/orchestrator/sessions/{session_id}",
            json={},
            headers=headers,
        )
        response = await client.post(
            f"{agent_url}/run",
            json={
                "appName": app_name,
                "userId": "orchestrator",
                "sessionId": session_id,
                "newMessage": {
                    "role": "user",
                    "parts": [{"text": json.dumps(payload)}],
                },
            },
            headers=headers,
        )
        response.raise_for_status()
        events = response.json()

    if isinstance(events, list):
        for event in reversed(events):
            content = event.get("content", {})
            if not content:
                continue
            for part in content.get("parts", []):
                if "text" in part:
                    try:
                        return json.loads(part["text"])
                    except (json.JSONDecodeError, TypeError):
                        pass
    return {}


async def route(
    *,
    input: OrchestratorInput,
    postgres: PostgresClient,
    provisioning_agent: SubAgentClient,
    enquiry_agent: SubAgentClient,
    faq_agent: SubAgentClient | None = None,
    classifier: ClassifierClient | None = None,
    guardrails: DeveloperGuardrails | None = None,
) -> OrchestratorOutput:
    """Core orchestrator routing logic (injectable for testing)."""
    if guardrails is None:
        guardrails = _default_guardrails()

    classifier_client = classifier if classifier is not None else _DefaultClassifier()
    classification: ClassificationResult = await classifier_client.classify(
        input.raw_input, input.channel
    )

    if classification.confidence < 0.55:
        if input.channel == ChannelType.email:
            return OrchestratorOutput(
                correlation_id=input.correlation_id,
                request_id=input.request_id,
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
            correlation_id=input.correlation_id,
            request_id=input.request_id,
            outcome=Outcome.clarification_needed,
            intent=IntentType(classification.intent) if classification.intent in IntentType._value2member_map_ else None,
            confidence=classification.confidence,
            clarification_question=question,
        )

    # Validate developer guardrails for all provisioning resource types
    if classification.intent == "provision" and input.user_role == UserRoleType.developer:
        n = classification.normalized
        guardrail_result = validate_provisioning_guardrails(
            resource_type=n.resource_type if n else "compute_instance",
            region=n.region if n and hasattr(n, "region") else "",
            machine_type=n.machine_type if isinstance(n, NormalizedVMRequest) else None,
            storage_class=n.storage_class if isinstance(n, NormalizedBucketRequest) else None,
            user_role=input.user_role,
            guardrails=guardrails,
        )
        if not guardrail_result.passed:
            violations = [
                {"field": v.field, "provided": v.provided, "allowed": v.allowed}
                for v in guardrail_result.violations
            ]
            return OrchestratorOutput(
                correlation_id=input.correlation_id,
                request_id=input.request_id,
                outcome=Outcome.guardrail_violation,
                intent=IntentType.provision,
                confidence=classification.confidence,
                violations=violations,
            )

    # Daily rate limit check (developers only)
    if classification.intent == "provision" and input.user_role == UserRoleType.developer:
        usage = await postgres.increment_daily_usage(
            requesting_user=input.requesting_user,
            daily_limit=guardrails.daily_provisioning_limit,
        )
        if usage.get("limit_reached"):
            return OrchestratorOutput(
                correlation_id=input.correlation_id,
                request_id=input.request_id,
                outcome=Outcome.rate_limited,
                intent=IntentType.provision,
                confidence=classification.confidence,
            )

    # Route to sub-agent
    infra_request_id = str(uuid.uuid4())
    n = classification.normalized
    if classification.intent == "provision":
        missing: list[str] = []
        resource_name = (n.resource_name if n and hasattr(n, "resource_name") else "") or ""
        resource_type = n.resource_type if n else "compute_instance"
        if not resource_name:
            missing.append("a name for the resource (e.g. 'my-vm-1')")
        if isinstance(n, NormalizedVMRequest) and not n.machine_type:
            missing.append("the machine type (e.g. 'e2-standard-2' for 2 vCPU / 8 GB)")
        if isinstance(n, NormalizedVMRequest) and not n.region:
            missing.append("the region (e.g. 'us-central1')")
        if missing:
            question = (
                f"To provision a {resource_type.replace('_', ' ')}, I still need: "
                + ", ".join(missing)
                + ". Could you provide these details?"
            )
            return OrchestratorOutput(
                correlation_id=input.correlation_id,
                request_id=input.request_id,
                outcome=Outcome.clarification_needed,
                intent=IntentType.provision,
                confidence=classification.confidence,
                clarification_question=question,
            )
        sub_result = await provisioning_agent.submit(
            correlation_id=str(input.correlation_id),
            request_id=str(input.request_id),
            infra_request_id=infra_request_id,
            resource_type=resource_type,
            resource_name=resource_name,
            region=n.region if n and hasattr(n, "region") else "",
            zone=n.zone if isinstance(n, (NormalizedVMRequest, NormalizedEnquiryRequest)) else None,
            parameters=n.as_parameters() if n and hasattr(n, "as_parameters") else {},
            requesting_user=input.requesting_user,
            user_role=input.user_role.value if hasattr(input.user_role, "value") else str(input.user_role),
        )
    elif classification.intent == "enquiry":
        enq = n if isinstance(n, NormalizedEnquiryRequest) else None
        sub_result = await enquiry_agent.submit(
            correlation_id=str(input.correlation_id),
            request_id=str(input.request_id),
            query_type=enq.query_type if enq else "single",
            resource_type=enq.resource_type if enq else "compute_instance",
            resource_name=enq.resource_name if enq else None,
            project_id=(enq.project_id if enq else None) or _PROJECT_ID or "default",
            zone=enq.zone if enq else None,
            region=enq.region if enq else None,
            requesting_user=input.requesting_user,
            user_role=input.user_role,
        )
    elif classification.intent == "faq":
        faq_url = os.environ.get("FAQ_AGENT_URL", "http://faq-agent:8004")
        _faq_agent = faq_agent if faq_agent is not None else _A2AClient(faq_url)
        faq_n = n if isinstance(n, NormalizedFAQRequest) else None
        sub_result = await _faq_agent.submit(
            correlation_id=str(input.correlation_id),
            request_id=str(input.request_id),
            question=faq_n.question if faq_n else input.raw_input,
            requesting_user=input.requesting_user,
        )
    else:
        sub_result = {}

    return OrchestratorOutput(
        correlation_id=input.correlation_id,
        request_id=input.request_id,
        outcome=Outcome.routed,
        intent=IntentType(classification.intent) if classification.intent in IntentType._value2member_map_ else None,
        confidence=classification.confidence,
        sub_agent_result=sub_result,
    )


class _DefaultClassifier(ClassifierClient):
    async def classify(self, raw_input: str, channel: str) -> ClassificationResult:  # noqa: D401
        return await classify(raw_input, channel)


class _DefaultPostgresClient:
    async def increment_daily_usage(self, requesting_user: str, daily_limit: int) -> dict:
        return await _pg_increment_daily_usage(requesting_user, daily_limit)

    async def get_user_role(self, user_id: str) -> dict:
        return {}


class _A2AClient:
    def __init__(self, url: str) -> None:
        self._url = url

    async def submit(self, **kwargs: Any) -> dict:
        serializable = {
            k: dataclasses.asdict(v) if dataclasses.is_dataclass(v) else v
            for k, v in kwargs.items()
        }
        return await _call_sub_agent(
            self._url,
            {
                "id": str(uuid.uuid4()),
                "message": {
                    "role": "user",
                    "parts": [{"type": "data", "data": serializable}],
                },
            },
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
        provisioning_url = os.environ.get(
            "PROVISIONING_AGENT_URL", "http://provisioning-agent:8002"
        )
        enquiry_url = os.environ.get("ENQUIRY_AGENT_URL", "http://enquiry-agent:8003")
        faq_url = os.environ.get("FAQ_AGENT_URL", "http://faq-agent:8004")

        # Set correlation context
        ctx_corr = CorrelationContext(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
        )
        set_correlation_context(ctx_corr)

        output = await route(
            input=inp,
            postgres=_DefaultPostgresClient(),
            provisioning_agent=_A2AClient(provisioning_url),
            enquiry_agent=_A2AClient(enquiry_url),
            faq_agent=_A2AClient(faq_url),
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
