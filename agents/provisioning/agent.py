"""T047 — Provisioning Agent: Google ADK-native implementation.

Uses google-adk BaseAgent with Runner + InMemorySessionService.
Exposes root_agent for ADK AgentLoader discovery.

Served via ADK's get_fast_api_app (a2a=True) in __main__.

Input: user message parts[0].text = JSON-serialised ProvisioningInput

confirmed=False (pre-confirmation):
  - Compute SHA-256 idempotency key from resource_type:name:region
  - Check for existing job (return it if found)
  - Create ProvisioningJob with status awaiting_confirmation
  - Return confirmation_summary via confirmation.py builder
  - Return expires_at = now + 20 minutes

confirmed=True (post-confirmation):
  - Update InfraRequest to confirmed
  - Update ProvisioningJob to queued
  - Publish ProvisioningRequestEvent to PubSub via pubsub-mcp
  - Emit request_confirmed audit event

Output: single Event with parts[0].text = JSON ProvisioningConfirmationOutput | ProvisioningQueuedOutput
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Protocol

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types as genai_types

from agents.provisioning.confirmation import build_confirmation_summary
from contracts.agents.provisioning import (
    BucketParameters,
    ProvisioningConfirmationOutput,
    ProvisioningInput,
    ProvisioningQueuedOutput,
    VMParameters,
    VPCParameters,
)
from contracts.events.pubsub_events import ProvisioningRequestEvent
from contracts.shared.correlation import (
    new_correlation_context,
    set_correlation_context,
)
from contracts.shared.logging import configure_logging, get_logger
from contracts.shared.metrics import start_metrics_server
from mcp_servers.postgres import server as _pg_server
from mcp_servers.pubsub import server as _ps_server

configure_logging(service_name="provisioning-agent")
logger = get_logger("provisioning-agent")


class PostgresClient(Protocol):
    async def get_provisioning_job_by_idempotency_key(self, idempotency_key: str) -> dict: ...
    async def create_provisioning_job(self, job_data: dict) -> dict: ...
    async def update_job_status(self, job_id: str, status: str) -> dict: ...
    async def update_request_status(
        self, infra_request_id: str, status: str, confirmed_at: str | None
    ) -> dict: ...
    async def create_audit_event(self, event_data: dict) -> dict: ...


class PubSubClient(Protocol):
    async def publish_provisioning_request(self, event: dict) -> dict: ...


def _make_idempotency_key(resource_type: str, resource_name: str, region: str) -> str:
    raw = f"{resource_type}:{resource_name}:{region}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _params_to_dict(
    inp: ProvisioningInput,
) -> tuple[VMParameters | BucketParameters | VPCParameters | dict, dict[str, str]]:
    """Parse parameters into typed model and collect defaults applied."""
    defaults_applied: dict[str, str] = {}
    params = inp.parameters

    if isinstance(params, dict):
        if inp.resource_type.value == "compute_instance":
            typed = VMParameters(**params)
            if "machine_type" not in params:
                defaults_applied["machine_type"] = typed.machine_type
            if "disk_size_gb" not in params:
                defaults_applied["disk_size_gb"] = str(typed.disk_size_gb)
            if "image_family" not in params:
                defaults_applied["image_family"] = typed.image_family
            return typed, defaults_applied

        if inp.resource_type.value == "storage_bucket":
            typed = BucketParameters(**params)  # type: ignore[arg-type]
            if "storage_class" not in params:
                defaults_applied["storage_class"] = typed.storage_class
            return typed, defaults_applied

        if inp.resource_type.value == "vpc_network":
            typed = VPCParameters(**params)  # type: ignore[arg-type]
            return typed, defaults_applied

    return params, defaults_applied


async def handle_task(
    inp: ProvisioningInput,
    postgres: PostgresClient,
    pubsub: PubSubClient,
) -> ProvisioningConfirmationOutput | ProvisioningQueuedOutput:
    """Core provisioning agent logic (injectable for testing)."""
    idempotency_key = _make_idempotency_key(
        inp.resource_type.value, inp.resource_name, inp.region
    )

    if not inp.confirmed:
        existing = await postgres.get_provisioning_job_by_idempotency_key(
            idempotency_key=idempotency_key
        )
        if existing:
            logger.info(
                "provisioning_idempotency_hit",
                idempotency_key=idempotency_key,
                job_id=existing.get("id"),
            )
            return ProvisioningConfirmationOutput(
                correlation_id=inp.correlation_id,
                request_id=inp.request_id,
                job_id=uuid.UUID(existing["id"]),
                confirmation_summary=existing.get("confirmation_summary", ""),
                idempotency_key=idempotency_key,
                existing_job=existing,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
            )

        typed_params, defaults_applied = _params_to_dict(inp)
        confirmation_summary = build_confirmation_summary(
            params=typed_params,
            resource_name=inp.resource_name,
            region=inp.region,
            resource_type=inp.resource_type.value,
            zone=inp.zone,
            defaults_applied=defaults_applied,
        )
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)

        job = await postgres.create_provisioning_job({
            "infra_request_id": str(inp.infra_request_id),
            "idempotency_key": idempotency_key,
            "resource_type": inp.resource_type.value,
            "resource_name": inp.resource_name,
            "region": inp.region,
            "zone": inp.zone,
            "parameters": inp.parameters if isinstance(inp.parameters, dict) else inp.parameters.model_dump(),
            "requesting_user": inp.requesting_user,
            "user_role": inp.user_role.value,
            "status": "awaiting_confirmation",
            "expires_at": expires_at.isoformat(),
        })

        logger.info("provisioning_job_created", job_id=job["id"], idempotency_key=idempotency_key)

        return ProvisioningConfirmationOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            job_id=uuid.UUID(job["id"]),
            confirmation_summary=confirmation_summary,
            idempotency_key=idempotency_key,
            existing_job=None,
            expires_at=expires_at,
        )

    # confirmed=True: transition states, publish, audit
    existing = await postgres.get_provisioning_job_by_idempotency_key(
        idempotency_key=idempotency_key
    )
    if not existing:
        raise ValueError(f"No job found for idempotency_key={idempotency_key}")

    job_id = uuid.UUID(existing["id"])
    confirmed_at = datetime.now(timezone.utc)

    await postgres.update_request_status(
        infra_request_id=str(inp.infra_request_id),
        status="confirmed",
        confirmed_at=confirmed_at.isoformat(),
    )
    await postgres.update_job_status(job_id=str(job_id), status="queued")

    event = ProvisioningRequestEvent(
        job_id=job_id,
        infra_request_id=inp.infra_request_id,
        correlation_id=inp.correlation_id,
        idempotency_key=idempotency_key,
        resource_type=inp.resource_type,
        resource_name=inp.resource_name,
        region=inp.region,
        zone=inp.zone,
        parameters=inp.parameters if isinstance(inp.parameters, dict) else inp.parameters.model_dump(),
        requesting_user=inp.requesting_user,
        user_role=inp.user_role,
        published_at=confirmed_at,
    )
    await pubsub.publish_provisioning_request(event=event.model_dump(mode="json"))

    await postgres.create_audit_event({
        "event_type": "request_confirmed",
        "actor": inp.requesting_user,
        "agent_name": "provisioning-agent",
        "resource_type": inp.resource_type.value,
        "resource_name": inp.resource_name,
        "correlation_id": str(inp.correlation_id),
        "request_id": str(inp.request_id),
        "payload": {"job_id": str(job_id)},
    })

    logger.info("provisioning_job_queued", job_id=str(job_id))

    return ProvisioningQueuedOutput(
        correlation_id=inp.correlation_id,
        request_id=inp.request_id,
        job_id=job_id,
    )


class _DefaultPostgresClient:
    async def get_provisioning_job_by_idempotency_key(self, idempotency_key: str) -> dict:
        return await _pg_server.get_provisioning_job_by_idempotency_key(idempotency_key)  # type: ignore[arg-type]

    async def create_provisioning_job(self, job_data: dict) -> dict:
        return await _pg_server.create_provisioning_job(job_data)  # type: ignore[arg-type]

    async def update_job_status(self, job_id: str, status: str) -> dict:
        return await _pg_server.update_job_status(job_id=job_id, status=status)  # type: ignore[arg-type]

    async def update_request_status(self, infra_request_id: str, status: str, confirmed_at: str | None) -> dict:
        return await _pg_server.update_request_status(infra_request_id=infra_request_id, status=status, confirmed_at=confirmed_at)  # type: ignore[arg-type]

    async def create_audit_event(self, event_data: dict) -> dict:
        return await _pg_server.create_audit_event(event_data)  # type: ignore[arg-type]


class _DefaultPubSubClient:
    async def publish_provisioning_request(self, event: dict) -> dict:
        return _ps_server.publish_provisioning_request(event)  # type: ignore[arg-type]


# ─── ADK Agent ──────────────────────────────────────────────────────────────

class ProvisioningAgent(BaseAgent):
    """ADK BaseAgent implementing idempotent provisioning flow.

    Input: user message parts[0].text = JSON-serialised ProvisioningInput
    Output: single Event with parts[0].text = JSON ProvisioningConfirmationOutput
            or ProvisioningQueuedOutput
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        user_text = ""
        if ctx.user_content and ctx.user_content.parts:
            user_text = ctx.user_content.parts[0].text or ""

        try:
            task_data = json.loads(user_text)
            inp = ProvisioningInput(**task_data)
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

        # Set correlation context
        ctx_corr = new_correlation_context()
        set_correlation_context(ctx_corr)

        try:
            output = await handle_task(
                inp=inp,
                postgres=_DefaultPostgresClient(),
                pubsub=_DefaultPubSubClient(),
            )
        except ValueError as exc:
            error_out = {"error": str(exc)}
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=json.dumps(error_out))],
                ),
            )
            return

        logger.info(
            "provisioning_agent_response",
            status=output.status,
            job_id=str(output.job_id),
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
root_agent = ProvisioningAgent(
    name="provisioning_agent",
    description=(
        "Validates provisioning parameters, enforces idempotency, generates confirmation "
        "summaries, and publishes provisioning requests to PubSub after user confirmation."
    ),
)


# ─── Standalone HTTP server ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get("PORT", "8002"))
    start_metrics_server(port=9002)

    app = get_fast_api_app(
        agents_dir=agents_dir,
        web=False,
        a2a=True,
        host="0.0.0.0",
        port=port,
        allow_origins=["*"],
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
