"""T053 — /jobs router.

POST /jobs/{job_id}/confirm — call Provisioning Agent A2A with confirmed=True
POST /jobs/{job_id}/cancel  — cancel from awaiting_confirmation or queued
GET  /jobs/{job_id}         — current job status
GET  /jobs                  — list with status filter and limit/offset pagination
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from contracts.shared.correlation import new_correlation_context, set_correlation_context
from contracts.shared.logging import get_logger

logger = get_logger("jobs-router")
router = APIRouter(tags=["jobs"])

_PROVISIONING_URL = os.environ.get("PROVISIONING_AGENT_URL", "http://provisioning-agent:8002")

_CANCELLABLE_STATUSES = {"awaiting_confirmation", "queued"}


def _error_response(status: int, error_code: str, message: str, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "details": {},
        "correlation_id": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


async def _get_job_or_404(job_id: str, user_id: str) -> dict[str, Any]:
    from mcp_servers.postgres import server as pg

    job = await pg.get_provisioning_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("requesting_user") != user_id:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("/jobs/{job_id}/confirm")
async def confirm_job(job_id: uuid.UUID, request: Request) -> JSONResponse:
    ctx = new_correlation_context()
    set_correlation_context(ctx)

    user_id: str = getattr(request.state, "user_id", "")
    user_role_dict: dict = getattr(request.state, "user_role", {})
    user_role = user_role_dict.get("role", "developer")

    job = await _get_job_or_404(str(job_id), user_id)

    if job.get("status") not in {"awaiting_confirmation"}:
        return _error_response(409, "IDEMPOTENCY_CONFLICT", f"Job is in '{job.get('status')}' state and cannot be confirmed.")

    task_data = {
        "correlation_id": str(ctx.correlation_id),
        "request_id": str(uuid.uuid4()),
        "infra_request_id": job.get("infra_request_id"),
        "resource_type": job.get("resource_type"),
        "resource_name": job.get("resource_name"),
        "region": job.get("region"),
        "zone": job.get("zone"),
        "parameters": job.get("parameters", {}),
        "requesting_user": user_id,
        "user_role": user_role,
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
            result = response.json()
            artifacts = result.get("artifacts", [])
            sub_result: dict[str, Any] = {}
            if artifacts:
                parts = artifacts[0].get("parts", [])
                if parts:
                    sub_result = parts[0].get("data", {})
    except httpx.HTTPError as exc:
        logger.error("provisioning_confirm_failed", job_id=str(job_id), error=str(exc))
        raise HTTPException(status_code=502, detail="Provisioning agent unavailable.")

    return JSONResponse(
        status_code=200,
        content={
            "job_id": str(job_id),
            "status": sub_result.get("status", "queued"),
            "message": f"Provisioning job queued. Track progress at /api/v1/jobs/{job_id}/stream",
            "correlation_id": str(ctx.correlation_id),
        },
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: uuid.UUID, request: Request) -> JSONResponse:
    ctx = new_correlation_context()
    set_correlation_context(ctx)

    user_id: str = getattr(request.state, "user_id", "")
    job = await _get_job_or_404(str(job_id), user_id)

    if job.get("status") not in _CANCELLABLE_STATUSES:
        return _error_response(
            409,
            "JOB_NOT_CANCELLABLE",
            f"Job is in '{job.get('status')}' state and cannot be cancelled.",
        )

    from mcp_servers.postgres import server as pg

    await pg.cancel_job(str(job_id), requesting_user=user_id)

    return JSONResponse(
        status_code=200,
        content={
            "job_id": str(job_id),
            "status": "cancelled",
            "correlation_id": str(ctx.correlation_id),
        },
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, request: Request) -> JSONResponse:
    user_id: str = getattr(request.state, "user_id", "")
    job = await _get_job_or_404(str(job_id), user_id)

    return JSONResponse(
        status_code=200,
        content={
            "job_id": job.get("id"),
            "resource_type": job.get("resource_type"),
            "resource_name": job.get("resource_name"),
            "region": job.get("region"),
            "status": job.get("status"),
            "retry_count": job.get("retry_count", 0),
            "gcp_resource_id": job.get("gcp_resource_id"),
            "error_message": job.get("error_message"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "completed_at": job.get("completed_at"),
            "correlation_id": job.get("correlation_id"),
        },
    )


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    user_id: str = getattr(request.state, "user_id", "")

    from mcp_servers.postgres import server as pg

    result = await pg.list_provisioning_jobs(
        requesting_user=user_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    jobs = result.get("jobs", [])
    total = result.get("total", len(jobs))

    return JSONResponse(
        status_code=200,
        content={
            "jobs": [
                {
                    "job_id": j.get("id"),
                    "resource_type": j.get("resource_type"),
                    "resource_name": j.get("resource_name"),
                    "region": j.get("region"),
                    "status": j.get("status"),
                    "retry_count": j.get("retry_count", 0),
                    "gcp_resource_id": j.get("gcp_resource_id"),
                    "created_at": j.get("created_at"),
                    "updated_at": j.get("updated_at"),
                }
                for j in jobs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )
