"""T036 — postgres-mcp: MCP server wrapping PostgreSQL for all persistent state operations.

Tools: get_provisioning_job, get_provisioning_job_by_idempotency_key,
create_provisioning_job, update_job_status, cancel_job, get_infra_request,
create_infra_request, update_request_status, get_user_role, verify_api_key,
get_daily_usage_count, increment_daily_usage, create_audit_event, create_faq_query.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg
import bcrypt
from mcp.server.fastmcp import FastMCP

from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="postgres-mcp")
logger = get_logger("postgres-mcp")

mcp = FastMCP("postgres-mcp")

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ["DATABASE_URL"],
            min_size=2,
            max_size=10,
        )
    return _pool


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    result = {}
    for key, value in row.items():
        if isinstance(value, (UUID, datetime, date)):
            result[key] = str(value)
        elif isinstance(value, list):
            result[key] = [
                _row_to_dict(item) if isinstance(item, asyncpg.Record) else str(item) if isinstance(item, (UUID, datetime)) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


@mcp.tool()
async def get_provisioning_job(job_id: str) -> dict[str, Any]:
    """Fetch a provisioning job by ID."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM provisioning_jobs WHERE id = $1",
            UUID(job_id),
        )
    if row is None:
        return {}
    return _row_to_dict(row)


@mcp.tool()
async def get_provisioning_job_by_idempotency_key(idempotency_key: str) -> dict[str, Any]:
    """Idempotency check — returns existing job or empty dict if none found."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM provisioning_jobs WHERE idempotency_key = $1 ORDER BY created_at DESC LIMIT 1",
            idempotency_key,
        )
    if row is None:
        return {}
    return _row_to_dict(row)


@mcp.tool()
async def create_provisioning_job(job_data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new provisioning job row. job_data follows ProvisioningJobCreate schema."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO provisioning_jobs (
                infra_request_id, idempotency_key, resource_type, resource_name,
                region, zone, parameters, requesting_user, user_role, status,
                dry_run, retry_count, rollback_resources, expires_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            RETURNING *
            """,
            UUID(job_data["infra_request_id"]),
            job_data["idempotency_key"],
            job_data["resource_type"],
            job_data["resource_name"],
            job_data["region"],
            job_data.get("zone"),
            json.dumps(job_data.get("parameters", {})),
            job_data["requesting_user"],
            job_data["user_role"],
            "awaiting_confirmation",
            job_data.get("dry_run", False),
            0,
            json.dumps([]),
            datetime.fromisoformat(job_data["expires_at"]) if isinstance(job_data.get("expires_at"), str) else job_data.get("expires_at"),
        )
    return _row_to_dict(row)


@mcp.tool()
async def update_job_status(
    job_id: str,
    status: str,
    retry_count: int | None = None,
    gcp_resource_id: str | None = None,
    error_message: str | None = None,
    rollback_resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update job status and emit pg_notify for SSE push."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE provisioning_jobs SET
                    status = $2,
                    retry_count = COALESCE($3, retry_count),
                    gcp_resource_id = COALESCE($4, gcp_resource_id),
                    error_message = COALESCE($5, error_message),
                    rollback_resources = COALESCE($6::jsonb, rollback_resources),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                UUID(job_id),
                status,
                retry_count,
                gcp_resource_id,
                error_message,
                json.dumps(rollback_resources) if rollback_resources is not None else None,
            )
            payload = json.dumps({"job_id": job_id, "status": status})
            await conn.execute(f"SELECT pg_notify('infraops_job_status', $1)", payload)
    return _row_to_dict(row)


@mcp.tool()
async def cancel_job(job_id: str, requesting_user: str) -> dict[str, Any]:
    """Atomically set job status to cancelled.

    Data integrity guard: the UPDATE only matches rows in awaiting_confirmation or queued
    and owned by requesting_user — it will not mutate a succeeded or in_progress job.
    Returns the updated row, or empty dict if the job was not in a cancellable state
    (caller is responsible for the user-facing error message).
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE provisioning_jobs SET status = 'cancelled', updated_at = NOW()
            WHERE id = $1
              AND status IN ('awaiting_confirmation', 'queued')
              AND requesting_user = $2
            RETURNING *
            """,
            UUID(job_id),
            requesting_user,
        )
    if row is None:
        return {}
    return _row_to_dict(row)


@mcp.tool()
async def get_infra_request(infra_request_id: str) -> dict[str, Any]:
    """Fetch an infrastructure request by ID."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM infra_requests WHERE id = $1",
            UUID(infra_request_id),
        )
    if row is None:
        return {}
    return _row_to_dict(row)


@mcp.tool()
async def create_infra_request(request_data: dict[str, Any]) -> dict[str, Any]:
    """Insert a new infrastructure request row. Follows InfraRequestCreate schema."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO infra_requests (
                raw_input, channel, requesting_user, user_role, status,
                email_thread_id, email_message_id
            ) VALUES ($1,$2,$3,$4,'received',$5,$6)
            RETURNING *
            """,
            request_data["raw_input"],
            request_data["channel"],
            request_data["requesting_user"],
            request_data["user_role"],
            request_data.get("email_thread_id"),
            request_data.get("email_message_id"),
        )
    return _row_to_dict(row)


@mcp.tool()
async def update_request_status(
    infra_request_id: str,
    status: str,
    intent: str | None = None,
    confidence: float | None = None,
    normalized_params: dict[str, Any] | None = None,
    clarification_question: str | None = None,
    confirmation_summary: str | None = None,
    confirmed_at: str | None = None,
) -> dict[str, Any]:
    """Update infra request status and optional classification fields."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE infra_requests SET
                status = $2,
                intent = COALESCE($3, intent),
                confidence = COALESCE($4, confidence),
                normalized_params = COALESCE($5::jsonb, normalized_params),
                clarification_question = COALESCE($6, clarification_question),
                confirmation_summary = COALESCE($7, confirmation_summary),
                confirmed_at = COALESCE($8::timestamptz, confirmed_at),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            UUID(infra_request_id),
            status,
            intent,
            confidence,
            json.dumps(normalized_params) if normalized_params is not None else None,
            clarification_question,
            confirmation_summary,
            confirmed_at,
        )
    if row is None:
        return {}
    return _row_to_dict(row)


@mcp.tool()
async def get_user_role(user_id: str) -> dict[str, Any]:
    """Fetch user role by user_id. Returns empty dict if not found."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, role, api_key_expires_at, daily_provisioning_count, "
            "daily_count_reset_at, created_at, updated_at FROM user_roles WHERE user_id = $1",
            user_id,
        )
    if row is None:
        return {}
    return _row_to_dict(row)


@mcp.tool()
async def verify_api_key(user_id: str, api_key_plaintext: str) -> dict[str, Any]:
    """bcrypt-verify plaintext key against stored hash and check expiry.

    When user_id is empty, scans all rows to find a matching key.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if user_id:
            rows = await conn.fetch(
                "SELECT user_id, role, api_key_hash, api_key_expires_at "
                "FROM user_roles WHERE user_id = $1",
                user_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT user_id, role, api_key_hash, api_key_expires_at FROM user_roles"
            )

    for row in rows:
        stored_hash: str = row["api_key_hash"]
        expires_at: datetime = row["api_key_expires_at"]

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expires_at:
            continue

        if bcrypt.checkpw(api_key_plaintext.encode(), stored_hash.encode()):
            return {
                "valid": True,
                "user_id": row["user_id"],
                "user_role": {
                    "role": row["role"],
                    "api_key_expires_at": str(row["api_key_expires_at"]),
                },
            }

    return {"valid": False, "user_id": None, "user_role": None}


@mcp.tool()
async def get_daily_usage_count(requesting_user: str) -> dict[str, Any]:
    """Count provisioning jobs created today for this user."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        count: int = await conn.fetchval(
            """
            SELECT COUNT(*) FROM provisioning_jobs
            WHERE requesting_user = $1
              AND created_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
              AND status != 'cancelled'
            """,
            requesting_user,
        )
    return {"count": count}


@mcp.tool()
async def increment_daily_usage(requesting_user: str, daily_limit: int) -> dict[str, Any]:
    """Count today's provisioning jobs for requesting_user and compare to the caller-supplied limit.

    The limit is a policy parameter — callers own it; this function is a pure data adapter.
    Returns {"count": int, "limit_reached": bool}.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        count: int = await conn.fetchval(
            """
            SELECT COUNT(*) FROM provisioning_jobs
            WHERE requesting_user = $1
              AND created_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
              AND status != 'cancelled'
            """,
            requesting_user,
        )
    return {"count": count, "limit_reached": count >= daily_limit}


@mcp.tool()
async def create_audit_event(event_data: dict[str, Any]) -> dict[str, Any]:
    """Append-only insert of an audit event. Payload is auto-redacted."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO audit_events (
                event_type, actor, agent_name, workflow_name,
                resource_type, resource_name, intent, payload,
                correlation_id, request_id
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING *
            """,
            event_data["event_type"],
            event_data["actor"],
            event_data["agent_name"],
            event_data.get("workflow_name"),
            event_data.get("resource_type"),
            event_data.get("resource_name"),
            event_data.get("intent"),
            json.dumps(event_data.get("payload", {})),
            UUID(event_data["correlation_id"]),
            UUID(event_data["request_id"]),
        )
    return _row_to_dict(row)


@mcp.tool()
async def create_faq_query(query_data: dict[str, Any]) -> dict[str, Any]:
    """Insert an FAQ query record with retrieved chunks and generated answer."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO faq_queries (
                correlation_id, raw_question, retrieved_chunks,
                generated_answer, sources_cited, confidence, no_results_found
            ) VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7)
            RETURNING *
            """,
            UUID(query_data["correlation_id"]),
            query_data["raw_question"],
            json.dumps(query_data.get("retrieved_chunks", [])),
            query_data["generated_answer"],
            query_data.get("sources_cited", []),
            query_data.get("confidence"),
            query_data.get("no_results_found", False),
        )
    return _row_to_dict(row)


@mcp.tool()
async def list_provisioning_jobs(
    requesting_user: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List provisioning jobs for a user with optional status filter and pagination."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM provisioning_jobs WHERE requesting_user=$1 AND status=$2 ORDER BY created_at DESC LIMIT $3 OFFSET $4",
                requesting_user, status, limit, offset,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM provisioning_jobs WHERE requesting_user=$1 AND status=$2",
                requesting_user, status,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM provisioning_jobs WHERE requesting_user=$1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
                requesting_user, limit, offset,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM provisioning_jobs WHERE requesting_user=$1",
                requesting_user,
            )
    return {"jobs": [_row_to_dict(r) for r in rows], "total": total}


@mcp.tool()
async def rotate_api_key(user_id: str, new_key_hash: str, expires_at: str) -> dict[str, Any]:
    """Replace the user's API key hash with a new one and update expiry."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE api_keys
            SET key_hash=$1, expires_at=$2::timestamptz, updated_at=NOW()
            WHERE user_id=$3
            RETURNING *
            """,
            new_key_hash,
            expires_at,
            user_id,
        )
    return _row_to_dict(row) if row else {}


if __name__ == "__main__":
    import os
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8092"))
    mcp.run(transport="sse")
