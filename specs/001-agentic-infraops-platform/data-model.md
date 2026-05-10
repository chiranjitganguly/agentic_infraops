# Data Model: Agentic InfraOps Self-Service Platform (Phase 1)

**Branch**: `001-agentic-infraops-platform` | **Date**: 2026-05-10

## Entity Relationship Overview

```
UserRole ─────────────────────────────────────┐
    │                                          │
    │ (requesting_user)                        │
    ▼                                          ▼
InfraRequest ──────────────────► ProvisioningJob
    │                                   │
    │ (per intent)                       │ (on status change)
    ▼                                   ▼
FAQQuery                          AuditEvent ◄─── (all entities emit)
ResourceStatus ◄─── (enquiry)
```

---

## 1. InfraRequest

Represents a single user request received via chatbot web UI or email. Created at the moment of ingestion, before intent classification.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, non-null | Unique request identifier |
| `correlation_id` | UUID | non-null, indexed | Propagated across all derived events and jobs |
| `raw_input` | TEXT | non-null | Original unmodified user message or email body |
| `channel` | ENUM | `chatbot`, `email` | Input channel |
| `intent` | ENUM\|NULL | `provision`, `enquiry`, `faq` | Classified intent (NULL until classified) |
| `confidence` | FLOAT\|NULL | 0.0–1.0 | Classifier confidence score |
| `normalized_params` | JSONB | non-null, default `{}` | Structured parameters extracted from raw input |
| `requesting_user` | TEXT | non-null, indexed | User email or user_id |
| `user_role` | ENUM | `developer`, `platform_engineer` | Role at time of request |
| `status` | ENUM | non-null | See state machine below |
| `confirmation_summary` | TEXT\|NULL | | Human-readable summary shown to user before confirm |
| `created_at` | TIMESTAMPTZ | non-null, default NOW() | |
| `confirmed_at` | TIMESTAMPTZ\|NULL | | Set when user confirms |
| `expires_at` | TIMESTAMPTZ | non-null | `created_at + 20 minutes` for pending confirmation |
| `email_thread_id` | TEXT\|NULL | | Gmail thread ID (email channel only) |
| `email_message_id` | TEXT\|NULL | | Gmail message ID of the original inbound email |

### State Machine

```
received → classifying → awaiting_confirmation → confirmed → fulfilled
                                               ↓             ↓
                                           rejected       failed
                    ↓
                 clarifying → (back to received after user reply)
                    ↓
                 expired (20-minute timeout)
```

### Validation Rules

- `expires_at` MUST equal `created_at + INTERVAL '20 minutes'`
- `email_thread_id` and `email_message_id` MUST be non-null when `channel = 'email'`
- `normalized_params` MUST be valid JSON; structure validated against resource-type-specific schema at classification time
- `confidence` < 0.7 → status transitions to `clarifying` instead of `awaiting_confirmation`

---

## 2. ProvisioningJob

Tracks a single GCP resource provisioning operation through its full lifecycle.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, non-null | Unique job identifier |
| `infra_request_id` | UUID | FK → InfraRequest.id, non-null | Parent request |
| `correlation_id` | UUID | non-null, indexed | Propagated from InfraRequest |
| `idempotency_key` | TEXT | non-null, UNIQUE | SHA-256 of `resource_type + ':' + resource_name + ':' + region` |
| `resource_type` | ENUM | `compute_instance`, `storage_bucket`, `vpc_network` | |
| `resource_name` | TEXT | non-null | Target GCP resource name |
| `region` | TEXT | non-null | GCP region (e.g., `us-central1`) |
| `zone` | TEXT\|NULL | | GCP zone (compute instances only) |
| `parameters` | JSONB | non-null | Full normalized provisioning parameters |
| `status` | ENUM | non-null | See state machine below |
| `retry_count` | INTEGER | non-null, default 0, max 3 | |
| `gcp_resource_id` | TEXT\|NULL | | GCP-assigned resource ID after successful creation |
| `rollback_resources` | JSONB\|NULL | | List of created resources to delete on rollback |
| `error_message` | TEXT\|NULL | | Last error message from failed attempt |
| `requesting_user` | TEXT | non-null | Propagated from InfraRequest |
| `created_at` | TIMESTAMPTZ | non-null, default NOW() | |
| `updated_at` | TIMESTAMPTZ | non-null | Updated on every state transition |
| `completed_at` | TIMESTAMPTZ\|NULL | | Set when status reaches terminal state |
| `dry_run` | BOOLEAN | non-null, default FALSE | If TRUE, no GCP resources are created |

### State Machine

```
pending → in_progress → succeeded
              │
              ├──(transient failure)──► retrying ──► in_progress (up to 3 times)
              │                                  │
              │                           (exhausted) → rollback → failed
              │
              └──(terminal failure, no retry)──► rollback ──► failed

pending ──(user cancels)──► cancelled
```

### Validation Rules

- `idempotency_key` UNIQUE constraint enforced at database level
- On INSERT: if a row with the same `idempotency_key` exists in status `pending`, `in_progress`, `retrying`, or `succeeded` → return existing job (no new row)
- `retry_count` MUST NOT exceed 3; transition to `failed` after third exhausted retry
- `rollback_resources` MUST be populated before first GCP API call (populated during dry-run validation step in DAG)
- `updated_at` MUST be set via trigger on every UPDATE

### Indexes

- `UNIQUE (idempotency_key)`
- `INDEX (requesting_user, created_at DESC)` — for daily rate limit queries
- `INDEX (status, created_at)` — for pending job cleanup

---

## 3. ResourceStatus

A point-in-time snapshot of a GCP resource's status. Not persisted to PostgreSQL — returned directly from the enquiry agent's live GCP API call. Represented as a Pydantic model only.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `resource_type` | ENUM | `compute_instance`, `storage_bucket`, `vpc_network` |
| `resource_name` | TEXT | GCP resource name |
| `project_id` | TEXT | GCP project ID |
| `zone` | TEXT\|NULL | Zone (compute instances only) |
| `region` | TEXT\|NULL | Region (storage buckets, VPC networks) |
| `status` | TEXT | GCP-returned status string (e.g., `RUNNING`, `TERMINATED`, `ACTIVE`) |
| `metadata` | DICT | Resource-type-specific metadata (machine type, storage class, etc.) |
| `queried_at` | DATETIME | Timestamp of the GCP API call |
| `requested_by` | TEXT | Requesting user |
| `correlation_id` | UUID | Propagated from InfraRequest |

---

## 4. FAQQuery

Represents a single FAQ interaction — question, retrieved context, and generated answer.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, non-null | |
| `correlation_id` | UUID | non-null, indexed | |
| `raw_question` | TEXT | non-null | Original user question |
| `requesting_user` | TEXT | non-null | |
| `retrieved_chunks` | JSONB | non-null | List of `{chunk_text, source_doc, bm25_score, vector_score, final_score}` |
| `generated_answer` | TEXT | non-null | LLM-synthesised answer |
| `sources_cited` | JSONB | non-null | List of source document references |
| `answer_confidence` | FLOAT\|NULL | 0.0–1.0 | Model self-assessed confidence |
| `no_results_found` | BOOLEAN | non-null, default FALSE | TRUE if retrieval returned zero chunks above threshold |
| `created_at` | TIMESTAMPTZ | non-null, default NOW() | |

---

## 5. AuditEvent

Immutable record of every system action. Append-only — no UPDATE or DELETE permitted.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, non-null | |
| `event_type` | ENUM | non-null | See event types below |
| `actor` | TEXT | non-null | User email or agent name |
| `agent_name` | TEXT | non-null | Agent that emitted the event |
| `workflow_name` | TEXT\|NULL | | Airflow DAG name (workflow events only) |
| `resource_type` | TEXT\|NULL | | |
| `resource_name` | TEXT\|NULL | | |
| `intent` | TEXT\|NULL | | |
| `payload` | JSONB | non-null | Redacted event payload |
| `timestamp` | TIMESTAMPTZ | non-null, default NOW() | |
| `correlation_id` | UUID | non-null, indexed | |
| `request_id` | UUID | non-null, indexed | |

### Event Types

| Event Type | Emitted By | Description |
|------------|-----------|-------------|
| `request_received` | Orchestrator | New InfraRequest ingested |
| `intent_classified` | Orchestrator | Intent classification result |
| `clarification_requested` | Orchestrator | Low-confidence classification, asking user |
| `confirmation_sent` | Provisioning Agent | Confirmation summary sent to user |
| `request_confirmed` | Orchestrator | User confirmed provisioning |
| `request_rejected` | Orchestrator | User rejected or request invalid |
| `request_expired` | Orchestrator | 20-minute confirmation timeout |
| `guardrail_violation` | Orchestrator | Developer request outside allowed parameters |
| `rate_limit_exceeded` | Orchestrator | Developer daily limit reached |
| `job_created` | Provisioning Agent | ProvisioningJob row created |
| `job_started` | Airflow DAG | DAG picked up job from PubSub |
| `job_retried` | Airflow DAG | Retry attempt initiated |
| `job_succeeded` | Airflow DAG | GCP resource created successfully |
| `job_failed` | Airflow DAG | All retries exhausted, rollback complete |
| `job_cancelled` | Orchestrator | User cancelled pending job |
| `rollback_started` | Airflow DAG | Rollback task group started |
| `rollback_completed` | Airflow DAG | All created resources deleted |
| `status_queried` | Enquiry Agent | Resource status retrieved from GCP |
| `faq_answered` | FAQ Agent | FAQ response generated |
| `backstage_registered` | Provisioning Agent | Resource registered in Backstage catalog |

### Immutability Enforcement

```sql
CREATE RULE no_update_audit_events AS ON UPDATE TO audit_events DO INSTEAD NOTHING;
CREATE RULE no_delete_audit_events AS ON DELETE TO audit_events DO INSTEAD NOTHING;
```

---

## 6. UserRole

Stores user identity, role assignment, and API key for the custom web UI.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `user_id` | TEXT | PK, non-null | User email address |
| `role` | ENUM | `developer`, `platform_engineer` | |
| `api_key_hash` | TEXT | non-null | bcrypt hash of the API key |
| `api_key_expires_at` | TIMESTAMPTZ | non-null | `issued_at + 90 days` |
| `api_key_last_used` | TIMESTAMPTZ\|NULL | | Updated asynchronously on each request |
| `daily_provisioning_count` | INTEGER | non-null, default 0 | Resets at midnight UTC |
| `daily_count_reset_at` | TIMESTAMPTZ | non-null | Timestamp of last daily reset |
| `created_at` | TIMESTAMPTZ | non-null, default NOW() | |
| `updated_at` | TIMESTAMPTZ | non-null | |

### Developer Guardrails (enforced by Orchestrator)

| Parameter | Allowed Values for Developers |
|-----------|------------------------------|
| `region` | `us-central1`, `us-east1`, `europe-west1` (configurable at deploy time) |
| `machine_type` (VM) | `e2-standard-2`, `e2-standard-4`, `e2-standard-8` |
| `storage_class` (bucket) | `STANDARD`, `NEARLINE` |
| `daily_provisioning_limit` | 10 resources/day |
| `vpc_provisioning` | Not permitted |

Platform engineers: no guardrail restrictions.

---

## PostgreSQL Schema Summary

```sql
-- Enums
CREATE TYPE channel_type AS ENUM ('chatbot', 'email');
CREATE TYPE intent_type AS ENUM ('provision', 'enquiry', 'faq');
CREATE TYPE request_status AS ENUM ('received', 'classifying', 'clarifying', 'awaiting_confirmation', 'confirmed', 'rejected', 'expired', 'fulfilled', 'failed');
CREATE TYPE job_status AS ENUM ('pending', 'in_progress', 'retrying', 'rollback', 'succeeded', 'failed', 'cancelled');
CREATE TYPE resource_type AS ENUM ('compute_instance', 'storage_bucket', 'vpc_network');
CREATE TYPE user_role_type AS ENUM ('developer', 'platform_engineer');

-- Tables (abbreviated)
CREATE TABLE infra_requests (...);
CREATE TABLE provisioning_jobs (...);
CREATE TABLE faq_queries (...);
CREATE TABLE audit_events (...);
CREATE TABLE user_roles (...);

-- Triggers
CREATE TRIGGER set_updated_at BEFORE UPDATE ON provisioning_jobs
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

CREATE TRIGGER set_updated_at BEFORE UPDATE ON infra_requests
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- NOTIFY trigger for SSE
CREATE OR REPLACE FUNCTION notify_job_status_change() RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('infraops_job_status',
    json_build_object('job_id', NEW.id, 'status', NEW.status, 'updated_at', NEW.updated_at)::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER job_status_notify AFTER UPDATE OF status ON provisioning_jobs
  FOR EACH ROW EXECUTE FUNCTION notify_job_status_change();
```
