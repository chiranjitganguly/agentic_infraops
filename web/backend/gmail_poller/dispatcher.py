"""T057 — Email request and confirmation reply dispatcher.

dispatch_email_request(message) → (thread_id, infra_request_id) | None
  - All email requests treated as user_role=developer
  - Calls Orchestrator A2A
  - Low-confidence/rejected → sends rejection email
  - Provisioning → sends confirmation email with 20-min deadline
  - Returns (sent_thread_id, infra_request_id) so poller can track confirmation replies

dispatch_confirmation_reply(message, infra_request_id) → None
  - Calls Provisioning Agent A2A with confirmed=True
  - Sends status email to user
"""
from __future__ import annotations

import os
import uuid

import httpx

from contracts.shared.correlation import new_correlation_context, set_correlation_context
from contracts.shared.logging import get_logger

logger = get_logger("gmail-dispatcher")

_ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_AGENT_URL", "http://orchestrator-agent:8001")
_PROVISIONING_URL = os.environ.get("PROVISIONING_AGENT_URL", "http://provisioning-agent:8002")

_REJECTION_TEMPLATE = (
    "Hi,\n\n"
    "We couldn't understand your infrastructure request. Please try again with more detail.\n\n"
    "Examples:\n"
    "  - 'Create a VM with 4 CPUs in us-central1'\n"
    "  - 'What is the status of vm-my-server?'\n\n"
    "InfraOps Platform"
)

_CONFIRMATION_TEMPLATE = (
    "Hi,\n\n"
    "Please review the following provisioning request:\n\n"
    "{confirmation_summary}\n\n"
    "To confirm, reply to this email with 'Confirm' or 'Yes'.\n\n"
    "You have 20 minutes to confirm before this request expires.\n\n"
    "InfraOps Platform"
)

_QUEUED_TEMPLATE = (
    "Hi,\n\n"
    "Your provisioning request has been confirmed and queued for processing.\n\n"
    "Job ID: {job_id}\n\n"
    "You will receive another email when provisioning is complete.\n\n"
    "InfraOps Platform"
)


async def _call_orchestrator(task_data: dict) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{_ORCHESTRATOR_URL}/tasks",
            json={
                "id": str(uuid.uuid4()),
                "message": {"role": "user", "parts": [{"type": "data", "data": task_data}]},
            },
        )
        response.raise_for_status()
        result = response.json()
        artifacts = result.get("artifacts", [])
        if artifacts:
            parts = artifacts[0].get("parts", [])
            if parts:
                return parts[0].get("data", {})
    return {}


async def dispatch_email_request(message: dict) -> tuple[str, str] | None:
    """Dispatch an inbound email as an infrastructure request.

    Returns (thread_id, infra_request_id) when a confirmation email is sent,
    so the poller can watch for the reply.
    """
    from mcp_servers.gmail import server as gmail

    sender = message.get("from", "")
    body = message.get("body", "").strip()
    thread_id = message.get("thread_id")
    subject = message.get("subject", "InfraOps Request")

    ctx = new_correlation_context()
    set_correlation_context(ctx)

    infra_request_id = str(uuid.uuid4())

    task_data = {
        "correlation_id": str(ctx.correlation_id),
        "request_id": str(uuid.uuid4()),
        "raw_input": body,
        "channel": "email",
        "requesting_user": sender,
        "user_role": "developer",
        "email_thread_id": thread_id,
    }

    try:
        result = await _call_orchestrator(task_data)
    except httpx.HTTPError as exc:
        logger.error("email_orchestrator_failed", error=str(exc))
        return None

    outcome = result.get("outcome")

    if outcome in {"clarification_needed", "rejected", "guardrail_violation", "rate_limited"}:
        rejection_reason = result.get("rejection_reason") or _REJECTION_TEMPLATE
        gmail.send_email(
            to=sender,
            subject=f"Re: {subject}",
            body=rejection_reason,
            thread_id=thread_id,
        )
        logger.info("email_rejected", outcome=outcome, sender=sender)
        return None

    if outcome == "routed":
        sub_result = result.get("sub_agent_result") or {}
        intent = result.get("intent")

        if intent == "provision":
            confirmation_summary = sub_result.get("confirmation_summary", "")
            job_id = sub_result.get("job_id")
            body_text = _CONFIRMATION_TEMPLATE.format(confirmation_summary=confirmation_summary)

            sent = gmail.send_email(
                to=sender,
                subject=f"Re: {subject} — Please Confirm",
                body=body_text,
                thread_id=thread_id,
            )
            sent_thread_id = sent.get("thread_id") if sent else thread_id
            logger.info("email_confirmation_sent", job_id=job_id, thread_id=sent_thread_id)
            return sent_thread_id, infra_request_id

        answer = sub_result.get("answer", "")
        gmail.send_email(
            to=sender,
            subject=f"Re: {subject}",
            body=answer,
            thread_id=thread_id,
        )

    return None


async def dispatch_confirmation_reply(message: dict, infra_request_id: str) -> None:
    """Dispatch a confirmation reply to the Provisioning Agent."""
    from mcp_servers.gmail import server as gmail
    from mcp_servers.postgres import server as pg

    sender = message.get("from", "")
    thread_id = message.get("thread_id")

    try:
        infra_req = await pg.get_infra_request(infra_request_id)
    except Exception:
        logger.error("email_confirm_infra_request_not_found", infra_request_id=infra_request_id)
        return

    job_id = infra_req.get("job_id") or infra_req.get("provisioning_job_id")
    if not job_id:
        logger.error("email_confirm_no_job_id", infra_request_id=infra_request_id)
        return

    try:
        job = await pg.get_provisioning_job(job_id)
    except Exception:
        logger.error("email_confirm_job_not_found", job_id=job_id)
        return

    ctx = new_correlation_context()
    set_correlation_context(ctx)

    task_data = {
        "correlation_id": str(ctx.correlation_id),
        "request_id": str(uuid.uuid4()),
        "infra_request_id": infra_request_id,
        "resource_type": job.get("resource_type"),
        "resource_name": job.get("resource_name"),
        "region": job.get("region"),
        "zone": job.get("zone"),
        "parameters": job.get("parameters", {}),
        "requesting_user": sender,
        "user_role": "developer",
        "confirmed": True,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{_PROVISIONING_URL}/tasks",
                json={
                    "id": str(uuid.uuid4()),
                    "message": {"role": "user", "parts": [{"type": "data", "data": task_data}]},
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("email_confirm_provisioning_failed", job_id=job_id, error=str(exc))
        return

    gmail.send_email(
        to=sender,
        subject="InfraOps: Provisioning Confirmed",
        body=_QUEUED_TEMPLATE.format(job_id=job_id),
        thread_id=thread_id,
    )
    logger.info("email_confirmation_dispatched", job_id=job_id, sender=sender)
