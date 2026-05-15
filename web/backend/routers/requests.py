"""T052 — /requests router.

POST /requests: Submit a new NL request via the Orchestrator Agent.
POST /requests/{infra_request_id}/clarify: Provide clarification (max 2 rounds).

Handles all Orchestrator outcomes:
  clarification_needed → 200 + question
  guardrail_violation  → 403
  rate_limited         → 429
  rejected             → 400
  routed               → 202 (provisioning) or 200 (enquiry/faq)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from contracts.shared.correlation import new_correlation_context, set_correlation_context
from contracts.shared.logging import get_logger

logger = get_logger("requests-router")
router = APIRouter(tags=["requests"])

_ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_AGENT_URL", "http://orchestrator-agent:8001")

_MAX_CLARIFICATION_ROUNDS = 2


class SubmitRequestBody(BaseModel):
    raw_input: str = Field(min_length=1)
    channel: str = "web"


class ClarifyBody(BaseModel):
    clarification: str = Field(min_length=1)


def _error_response(status: int, error_code: str, message: str, details: dict | None = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "details": details or {},
        "correlation_id": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


async def _call_orchestrator(task_data: dict[str, Any]) -> dict[str, Any]:
    import json as _json
    user_id = task_data.get("requesting_user", "anonymous")
    session_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=60.0) as client:
        await client.post(
            f"{_ORCHESTRATOR_URL}/apps/orchestrator/users/{user_id}/sessions/{session_id}",
            json={},
        )
        response = await client.post(
            f"{_ORCHESTRATOR_URL}/run",
            json={
                "appName": "orchestrator",
                "userId": user_id,
                "sessionId": session_id,
                "newMessage": {
                    "role": "user",
                    "parts": [{"text": _json.dumps(task_data)}],
                },
            },
        )
        response.raise_for_status()
        events = response.json()

    # ADK returns a list of events; the orchestrator yields one event with parts[0].text = JSON
    if isinstance(events, list):
        for event in reversed(events):
            content = event.get("content", {})
            if not content:
                continue
            for part in content.get("parts", []):
                if "text" in part:
                    try:
                        return _json.loads(part["text"])
                    except (_json.JSONDecodeError, TypeError):
                        pass

    return {}


@router.post("/requests")
async def submit_request(body: SubmitRequestBody, request: Request) -> JSONResponse:
    ctx = new_correlation_context()
    set_correlation_context(ctx)

    user_id: str = getattr(request.state, "user_id", "")
    user_role_dict: dict = getattr(request.state, "user_role", {})
    user_role = user_role_dict.get("role", "developer")

    request_id = uuid.uuid4()
    infra_request_id = uuid.uuid4()

    task_data = {
        "correlation_id": str(ctx.correlation_id),
        "request_id": str(request_id),
        "raw_input": body.raw_input,
        "channel": body.channel,
        "requesting_user": user_id,
        "user_role": user_role,
    }

    try:
        result = await _call_orchestrator(task_data)
    except httpx.HTTPError as exc:
        logger.error("orchestrator_call_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Orchestrator agent unavailable.")

    outcome = result.get("outcome")

    if outcome == "clarification_needed":
        return JSONResponse(
            status_code=200,
            content={
                "infra_request_id": str(infra_request_id),
                "status": "clarification_needed",
                "clarification_question": result.get("clarification_question"),
                "correlation_id": str(ctx.correlation_id),
            },
        )

    if outcome == "guardrail_violation":
        return _error_response(403, "GUARDRAIL_VIOLATION", "Your request exceeds the allowed parameters for your role.")

    if outcome == "rate_limited":
        return _error_response(429, "RATE_LIMIT_EXCEEDED", "Daily provisioning limit reached. Resets at midnight UTC.")

    if outcome == "rejected":
        return _error_response(400, "VALIDATION_ERROR", result.get("rejection_reason", "Request could not be understood."))

    if outcome == "routed":
        sub_result = result.get("sub_agent_result") or {}
        intent = result.get("intent")

        if intent == "provision":
            status = sub_result.get("status", "awaiting_confirmation")
            if status == "awaiting_confirmation":
                return JSONResponse(
                    status_code=202,
                    content={
                        "infra_request_id": str(infra_request_id),
                        "job_id": sub_result.get("job_id"),
                        "intent": intent,
                        "status": status,
                        "confirmation_summary": sub_result.get("confirmation_summary"),
                        "answer": None,
                        "sources": [],
                        "expires_at": sub_result.get("expires_at"),
                        "correlation_id": str(ctx.correlation_id),
                    },
                )

        if intent == "enquiry":
            query_type = sub_result.get("query_type", "single")
            base = {
                "infra_request_id": str(infra_request_id),
                "intent": intent,
                "query_type": query_type,
                "status": "answered",
                "answer": sub_result.get("human_readable_summary") or sub_result.get("answer"),
                "queried_at": sub_result.get("queried_at"),
                "correlation_id": str(ctx.correlation_id),
            }
            if query_type == "list":
                base["resource_type"] = sub_result.get("resource_type")
                base["resources"] = sub_result.get("resources", [])
                base["total_count"] = sub_result.get("total_count", 0)
            else:
                base["resource_type"] = sub_result.get("resource_type")
                base["resource_name"] = sub_result.get("resource_name")
                base["gcp_status"] = sub_result.get("gcp_status")
                base["metadata"] = sub_result.get("metadata")
            return JSONResponse(status_code=200, content=base)

        return JSONResponse(
            status_code=200,
            content={
                "infra_request_id": str(infra_request_id),
                "intent": intent,
                "status": "answered",
                "answer": sub_result.get("answer"),
                "sources": sub_result.get("sources", []),
                "correlation_id": str(ctx.correlation_id),
            },
        )

    return _error_response(500, "INTERNAL_ERROR", f"Unexpected orchestrator outcome: {outcome}")


@router.post("/requests/{infra_request_id}/clarify")
async def clarify_request(
    infra_request_id: uuid.UUID,
    body: ClarifyBody,
    request: Request,
) -> JSONResponse:
    ctx = new_correlation_context()
    set_correlation_context(ctx)

    user_id: str = getattr(request.state, "user_id", "")
    user_role_dict: dict = getattr(request.state, "user_role", {})
    user_role = user_role_dict.get("role", "developer")

    try:
        from mcp_servers.postgres import server as pg

        infra_req = await pg.get_infra_request(str(infra_request_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Infra request not found.")

    clarification_rounds = infra_req.get("clarification_rounds", 0)
    if clarification_rounds >= _MAX_CLARIFICATION_ROUNDS:
        return _error_response(
            400,
            "VALIDATION_ERROR",
            f"Maximum clarification rounds ({_MAX_CLARIFICATION_ROUNDS}) reached. Please submit a new request.",
        )

    original_input = infra_req.get("raw_input", "")
    combined_input = f"{original_input}\nClarification: {body.clarification}"

    task_data = {
        "correlation_id": str(ctx.correlation_id),
        "request_id": str(uuid.uuid4()),
        "raw_input": combined_input,
        "channel": infra_req.get("channel", "web"),
        "requesting_user": user_id,
        "user_role": user_role,
    }

    try:
        result = await _call_orchestrator(task_data)
    except httpx.HTTPError as exc:
        logger.error("orchestrator_clarify_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Orchestrator agent unavailable.")

    outcome = result.get("outcome")

    if outcome == "clarification_needed":
        return JSONResponse(
            status_code=200,
            content={
                "infra_request_id": str(infra_request_id),
                "status": "clarification_needed",
                "clarification_question": result.get("clarification_question"),
                "clarification_round": clarification_rounds + 1,
                "correlation_id": str(ctx.correlation_id),
            },
        )

    if outcome == "guardrail_violation":
        return _error_response(403, "GUARDRAIL_VIOLATION", "Your request exceeds the allowed parameters for your role.")

    if outcome == "rate_limited":
        return _error_response(429, "RATE_LIMIT_EXCEEDED", "Daily provisioning limit reached.")

    if outcome == "rejected":
        return _error_response(400, "VALIDATION_ERROR", result.get("rejection_reason", "Request could not be understood."))

    if outcome == "routed":
        sub_result = result.get("sub_agent_result") or {}
        intent = result.get("intent")

        if intent == "provision":
            return JSONResponse(
                status_code=202,
                content={
                    "infra_request_id": str(infra_request_id),
                    "job_id": sub_result.get("job_id"),
                    "intent": intent,
                    "status": sub_result.get("status", "awaiting_confirmation"),
                    "confirmation_summary": sub_result.get("confirmation_summary"),
                    "expires_at": sub_result.get("expires_at"),
                    "correlation_id": str(ctx.correlation_id),
                },
            )

        if intent == "enquiry":
            query_type = sub_result.get("query_type", "single")
            base = {
                "infra_request_id": str(infra_request_id),
                "intent": intent,
                "query_type": query_type,
                "status": "answered",
                "answer": sub_result.get("human_readable_summary") or sub_result.get("answer"),
                "queried_at": sub_result.get("queried_at"),
                "correlation_id": str(ctx.correlation_id),
            }
            if query_type == "list":
                base["resource_type"] = sub_result.get("resource_type")
                base["resources"] = sub_result.get("resources", [])
                base["total_count"] = sub_result.get("total_count", 0)
            else:
                base["resource_type"] = sub_result.get("resource_type")
                base["resource_name"] = sub_result.get("resource_name")
                base["gcp_status"] = sub_result.get("gcp_status")
                base["metadata"] = sub_result.get("metadata")
            return JSONResponse(status_code=200, content=base)

        return JSONResponse(
            status_code=200,
            content={
                "infra_request_id": str(infra_request_id),
                "intent": intent,
                "status": "answered",
                "answer": sub_result.get("answer"),
                "sources": sub_result.get("sources", []),
                "correlation_id": str(ctx.correlation_id),
            },
        )

    return _error_response(500, "INTERNAL_ERROR", f"Unexpected orchestrator outcome: {outcome}")
