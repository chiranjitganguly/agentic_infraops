# ADR 0003: Airflow DAG is the Single Writer of ProvisioningJob State

**Date**: 2026-05-10
**Status**: Accepted

## Context

ProvisioningJob state transitions (`pending → in_progress → retrying → succeeded / failed / cancelled`) need to be written to PostgreSQL and communicated to the user (via SSE and email). Two services have visibility into job progress: the Airflow DAG (which executes the work) and a notification service (which could subscribe to PubSub status events). A decision was needed on which service owns the PostgreSQL write.

## Decision

The Airflow DAG is the single authoritative writer of ProvisioningJob state. At each state transition, the DAG:

1. Writes the new status to PostgreSQL via `postgres-mcp` (`update_job_status`)
2. Publishes a status event to the PubSub status topic

PostgreSQL LISTEN/NOTIFY (triggered by a database trigger on status updates) drives SSE to the user's browser automatically.

The notification service subscribes to PubSub for email delivery only. It never writes to PostgreSQL.

## Consequences

**Benefits**:
- Single writer eliminates dual-write race conditions between PubSub subscriber and DAG
- PostgreSQL state is always consistent with what Airflow has actually executed
- SSE is driven by the database trigger — it cannot diverge from the stored state
- Notification service is stateless and simple (read PubSub, send email)

**Costs**:
- Airflow DAGs have a dependency on `postgres-mcp` — DAGs are not purely workflow orchestration
- If `postgres-mcp` is unavailable, the DAG cannot record state transitions (mitigated by circuit breaker and Airflow retry)

**Alternative rejected**: Having the notification service write to PostgreSQL after reading from PubSub (Option B) — this creates a window where SSE could show a different state than what's in PostgreSQL if PubSub delivery is delayed or retried.
