"""T072 — Enquiry Agent: Google ADK implementation.

Handles single-resource status lookups and project-wide resource listing.
Emits a status_queried audit event via postgres-mcp on every successful query.

Input:  JSON-serialised EnquiryInput (query_type = "single" | "list")
Output: JSON-serialised EnquiryFoundOutput | EnquiryListOutput | EnquiryNotFoundOutput
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types as genai_types

from contracts.agents.enquiry import (
    EnquiryAccessDeniedOutput,
    EnquiryFoundOutput,
    EnquiryInput,
    EnquiryListOutput,
    ResourceType,
)
from contracts.schemas.audit_event import AuditEventCreate, AuditEventType
from contracts.shared.logging import configure_logging, get_logger
from contracts.shared.metrics import start_metrics_server
from skills.status_query.formatter import format_list_response, format_status_response
from skills.status_query.querier import list_resources, query_resource_status

configure_logging(service_name="enquiry-agent")
logger = get_logger("enquiry-agent")

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")


async def _emit_audit_event(inp: EnquiryInput, outcome: str) -> None:
    try:
        from mcp_servers.postgres.server import create_audit_event
        await create_audit_event(
            AuditEventCreate(
                event_type=AuditEventType.status_queried,
                actor=inp.requesting_user,
                agent_name="enquiry-agent",
                resource_type=inp.resource_type.value,
                resource_name=inp.resource_name or f"[list:{inp.resource_type.value}]",
                payload={"outcome": outcome, "query_type": inp.query_type},
                correlation_id=inp.correlation_id,
                request_id=inp.request_id,
            ).model_dump()
        )
    except Exception as exc:
        logger.warning("audit_event_failed", error=str(exc))


async def handle_enquiry(inp: EnquiryInput) -> dict:
    """Core enquiry logic — injectable for testing."""
    now = datetime.now(timezone.utc)
    project_id = inp.project_id or _PROJECT_ID

    if inp.query_type == "list":
        resources = list_resources(inp.resource_type, project_id)
        summary = format_list_response(resources, inp.resource_type)
        await _emit_audit_event(inp, "listed")
        return EnquiryListOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            resource_type=inp.resource_type,
            project_id=project_id,
            resources=resources,
            total_count=len(resources),
            human_readable_summary=summary,
            queried_at=now,
        ).model_dump(mode="json")

    # single lookup
    if not inp.resource_name:
        return EnquiryAccessDeniedOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            message="resource_name is required for single-resource queries.",
        ).model_dump(mode="json")

    result = query_resource_status(
        resource_type=inp.resource_type,
        resource_name=inp.resource_name,
        project_id=project_id,
        zone=inp.zone,
        region=inp.region,
    )

    if result.get("not_found"):
        from contracts.agents.enquiry import EnquiryNotFoundOutput
        await _emit_audit_event(inp, "not_found")
        return EnquiryNotFoundOutput(
            correlation_id=inp.correlation_id,
            request_id=inp.request_id,
            resource_type=inp.resource_type,
            resource_name=inp.resource_name,
            message=(
                f"No resource named '{inp.resource_name}' of type "
                f"'{inp.resource_type.value}' found in project '{project_id}'."
            ),
        ).model_dump(mode="json")

    metadata = result["metadata"]
    summary = format_status_response(
        metadata=metadata,
        gcp_status=result["gcp_status"],
        resource_name=result["resource_name"],
        resource_type=inp.resource_type,
    )
    await _emit_audit_event(inp, "found")
    return EnquiryFoundOutput(
        correlation_id=inp.correlation_id,
        request_id=inp.request_id,
        resource_type=inp.resource_type,
        resource_name=result["resource_name"],
        gcp_status=result["gcp_status"],
        metadata=metadata,
        human_readable_summary=summary,
        queried_at=result["queried_at"],
    ).model_dump(mode="json")


class EnquiryAgent(BaseAgent):
    """ADK BaseAgent for GCP resource status enquiries."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_text = ""
        if ctx.user_content and ctx.user_content.parts:
            user_text = ctx.user_content.parts[0].text or ""

        try:
            task_data = json.loads(user_text)
            # unwrap A2A envelope if present
            if "message" in task_data:
                parts = task_data["message"].get("parts", [])
                task_data = parts[0].get("data", {}) if parts else {}
            inp = EnquiryInput(**task_data)
        except Exception as exc:
            error_out = {"error": f"Invalid enquiry input: {exc}"}
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
            "enquiry_started",
            query_type=inp.query_type,
            resource_type=inp.resource_type.value,
            resource_name=inp.resource_name,
        )

        try:
            output = await handle_enquiry(inp)
        except Exception as exc:
            logger.error("enquiry_failed", error=str(exc))
            output = {
                "correlation_id": str(inp.correlation_id),
                "request_id": str(inp.request_id),
                "status": "error",
                "message": f"Enquiry failed: {exc}",
            }

        logger.info("enquiry_complete", status=output.get("status"))

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=json.dumps(output))],
            ),
        )


root_agent = EnquiryAgent(
    name="enquiry_agent",
    description="Queries live GCP resource status and lists project resources.",
)


if __name__ == "__main__":
    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get("PORT", "8003"))
    start_metrics_server(port=9003)

    app = get_fast_api_app(
        agents_dir=agents_dir,
        web=False,
        a2a=True,
        host="0.0.0.0",
        port=port,
        allow_origins=["*"],
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
