# PubSub Event Contracts

**Version**: 1.0.0 | **Date**: 2026-05-10
**Evolution policy**: Additive-only. New optional fields may be added. Field removals and type changes require a major version bump and a new topic.

---

## Topic: `infraops.provisioning.requests`

**Direction**: Provisioning Agent → Airflow DAG (via PubSubPullSensor)
**Subscription**: `infraops-provisioning-requests-sub` (one per DAG type: `-vm-sub`, `-bucket-sub`)
**Delivery**: At-least-once. Consumers MUST enforce idempotency via `idempotency_key`.

### Message Schema (v1)

```json
{
  "schema_version": "1.0.0",
  "event_type": "provisioning.request.created",
  "job_id": "<UUID>",
  "infra_request_id": "<UUID>",
  "correlation_id": "<UUID>",
  "idempotency_key": "<SHA-256 hex string>",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string>",
  "region": "<GCP region string>",
  "zone": "<GCP zone string | null>",
  "parameters": {
    "machine_type": "<string | null>",
    "disk_size_gb": "<integer | null>",
    "image_family": "<string | null>",
    "storage_class": "<string | null>",
    "network": "<string | null>",
    "subnet_cidr": "<string | null>"
  },
  "requesting_user": "<email string>",
  "user_role": "developer | platform_engineer",
  "dry_run": false,
  "published_at": "<ISO 8601 timestamp>"
}
```

### Attribute Filters (for DAG routing)

| Attribute | Value |
|-----------|-------|
| `resource_type` | `compute_instance` → `provision_vm_dag` |
| `resource_type` | `storage_bucket` → `provision_bucket_dag` |

---

## Topic: `infraops.provisioning.status`

**Direction**: Airflow DAG → Notification Service
**Subscription**: `infraops-provisioning-status-sub`
**Delivery**: At-least-once. Notification service deduplicates by `(job_id, status)`.

### Message Schema (v1)

```json
{
  "schema_version": "1.0.0",
  "event_type": "provisioning.job.status_changed",
  "job_id": "<UUID>",
  "infra_request_id": "<UUID>",
  "correlation_id": "<UUID>",
  "idempotency_key": "<string>",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string>",
  "status": "pending | in_progress | retrying | rollback | succeeded | failed | cancelled",
  "retry_count": "<integer 0-3>",
  "gcp_resource_id": "<string | null>",
  "error_message": "<string | null>",
  "requesting_user": "<email string>",
  "published_at": "<ISO 8601 timestamp>"
}
```

### Status Event Triggers

| Job Status | Trigger |
|-----------|---------|
| `in_progress` | DAG sensor picks up message from PubSub |
| `retrying` | Task group fails, retry policy applies |
| `rollback` | Retry count exhausted, rollback task group starts |
| `succeeded` | All tasks complete, GCP resource confirmed |
| `failed` | Rollback complete |
| `cancelled` | User cancels via web UI before DAG picks up message |

---

## Topic: `infraops.audit.events`

**Direction**: All agents and Airflow DAGs → Audit sink (PostgreSQL writer)
**Subscription**: `infraops-audit-events-sub`
**Delivery**: At-least-once. Audit writer uses `event_id` for deduplication.

### Message Schema (v1)

```json
{
  "schema_version": "1.0.0",
  "event_id": "<UUID>",
  "event_type": "<AuditEvent.event_type enum value>",
  "actor": "<user email or agent name>",
  "agent_name": "<string>",
  "workflow_name": "<string | null>",
  "resource_type": "<string | null>",
  "resource_name": "<string | null>",
  "intent": "<string | null>",
  "payload": "<JSONB — sensitive fields MUST be redacted before publishing>",
  "timestamp": "<ISO 8601 timestamp>",
  "correlation_id": "<UUID>",
  "request_id": "<UUID>"
}
```

### Redaction Rules

The following fields MUST be replaced with `"[REDACTED]"` before publishing to this topic:
- Any field named `api_key`, `api_key_hash`, `password`, `secret`, `token`
- Email body content in `raw_input` (replace with `"[REDACTED: email body]"`)
- `normalized_params.parameters` values for sensitive fields (retain keys, redact values)
