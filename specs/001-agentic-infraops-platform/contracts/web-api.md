# Web API Contract

**Base URL**: `http://localhost:8000/api/v1` (local) | `https://infraops.internal/api/v1` (production)
**Version**: 1.0.0 | **Date**: 2026-05-10
**Auth**: All endpoints require `X-API-Key: <key>` header. Missing or invalid keys return `401`.

---

## Authentication

### Verify Key and Get User Info

```
GET /auth/me
```

**Response 200**:
```json
{
  "user_id": "<email>",
  "role": "developer | platform_engineer",
  "api_key_expires_at": "<ISO 8601>",
  "daily_provisioning_count": 3,
  "daily_provisioning_limit": 10
}
```

**Response 401**: Invalid or expired API key.

---

### Rotate API Key

```
POST /auth/rotate-key
```

Requires current valid key. Issues a new key and immediately invalidates the old one.

**Response 200**:
```json
{
  "api_key": "<new plaintext key — shown once only>",
  "expires_at": "<ISO 8601>"
}
```

---

## Requests

### Submit a New Request

```
POST /requests
Content-Type: application/json
```

**Request body**:
```json
{
  "raw_input": "<natural language string>",
  "channel": "chatbot"
}
```

**Response 202** — Intent classified, awaiting confirmation:
```json
{
  "infra_request_id": "<UUID>",
  "job_id": "<UUID>",
  "intent": "provision | enquiry | faq",
  "status": "awaiting_confirmation | answered",
  "confirmation_summary": "<string | null>",
  "answer": "<string | null>",
  "sources": ["<string>"],
  "expires_at": "<ISO 8601 | null>",
  "correlation_id": "<UUID>"
}
```

**Response 200** — FAQ resolved immediately:
```json
{
  "infra_request_id": "<UUID>",
  "intent": "faq",
  "status": "answered",
  "answer": "<string>",
  "sources": ["<string>"],
  "correlation_id": "<UUID>"
}
```

**Response 200** — Enquiry resolved immediately (single resource):
```json
{
  "infra_request_id": "<UUID>",
  "intent": "enquiry",
  "query_type": "single",
  "status": "answered",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string>",
  "gcp_status": "<GCP status string, e.g. RUNNING | TERMINATED | ACTIVE>",
  "metadata": "<typed metadata object — see a2a-agents.md Enquiry Agent for per-type schemas>",
  "answer": "<human-readable summary string>",
  "queried_at": "<ISO 8601>",
  "correlation_id": "<UUID>"
}
```

**Response 200** — Enquiry resolved immediately (list):
```json
{
  "infra_request_id": "<UUID>",
  "intent": "enquiry",
  "query_type": "list",
  "status": "answered",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resources": [
    {
      "resource_name": "<string>",
      "gcp_status": "<string>",
      "zone_or_region": "<string | null>",
      "key_metadata": "<string>"
    }
  ],
  "total_count": "<int>",
  "answer": "<human-readable summary string>",
  "queried_at": "<ISO 8601>",
  "correlation_id": "<UUID>"
}
```

**Response 400** — Validation error:
```json
{
  "error_code": "VALIDATION_ERROR | GUARDRAIL_VIOLATION | RATE_LIMIT_EXCEEDED",
  "message": "<string>",
  "details": {}
}
```

**Response 409** — Idempotency conflict (duplicate provisioning request):
```json
{
  "error_code": "IDEMPOTENCY_CONFLICT",
  "message": "A provisioning job for this resource already exists.",
  "existing_job_id": "<UUID>",
  "existing_job_status": "<string>"
}
```

---

### Confirm a Pending Provisioning Request

```
POST /jobs/{job_id}/confirm
```

Transitions the job from `pending` (awaiting confirmation) to active in the queue.

**Response 200**:
```json
{
  "job_id": "<UUID>",
  "status": "pending",
  "message": "Provisioning job queued. Track progress at /api/v1/jobs/{job_id}/stream",
  "correlation_id": "<UUID>"
}
```

**Response 404**: Job not found or not owned by this user.
**Response 409**: Job already confirmed, cancelled, or expired.

---

### Cancel a Job

```
POST /jobs/{job_id}/cancel
```

Only valid for jobs in `pending` status (awaiting confirmation or queued but not yet picked up by Airflow).

**Response 200**:
```json
{
  "job_id": "<UUID>",
  "status": "cancelled",
  "correlation_id": "<UUID>"
}
```

**Response 409**: Job already in `in_progress` or terminal state — cannot cancel.

---

## Jobs

### Get Job Status

```
GET /jobs/{job_id}
```

**Response 200**:
```json
{
  "job_id": "<UUID>",
  "resource_type": "<string>",
  "resource_name": "<string>",
  "region": "<string>",
  "status": "pending | in_progress | retrying | rollback | succeeded | failed | cancelled",
  "retry_count": 0,
  "gcp_resource_id": "<string | null>",
  "error_message": "<string | null>",
  "created_at": "<ISO 8601>",
  "updated_at": "<ISO 8601>",
  "completed_at": "<ISO 8601 | null>",
  "correlation_id": "<UUID>"
}
```

---

### Stream Job Status (SSE)

```
GET /jobs/{job_id}/stream
Accept: text/event-stream
```

Server-Sent Events stream. The server pushes an event on each job status transition. The stream closes automatically when the job reaches a terminal state (`succeeded`, `failed`, `cancelled`).

**SSE Event format**:
```
event: job_status
data: {"job_id": "<UUID>", "status": "<string>", "retry_count": 0, "gcp_resource_id": "<string|null>", "error_message": "<string|null>", "updated_at": "<ISO 8601>"}

event: job_status
data: {"job_id": "<UUID>", "status": "succeeded", "gcp_resource_id": "projects/my-project/zones/us-central1-a/instances/web-server-1", "updated_at": "<ISO 8601>"}

event: done
data: {}
```

**Reconnection**: Client should set `EventSource` `reconnectDelay` to 5s. On reconnect, client fetches `GET /jobs/{job_id}` to get current state, then re-subscribes to the stream.

---

### Query GCP Resource Status (direct, bypasses NL classification)

```
GET /resources/{resource_type}/{resource_name}?project_id=<string>&zone=<string>
```

- `resource_type`: `compute_instance`, `storage_bucket`, or `vpc_network`
- `zone`: required for `compute_instance`; omit for bucket/VPC

**Response 200**:
```json
{
  "resource_type": "<string>",
  "resource_name": "<string>",
  "gcp_status": "<string>",
  "metadata": "<typed metadata object>",
  "human_readable_summary": "<string>",
  "queried_at": "<ISO 8601>"
}
```

**Response 404**: Resource not found in GCP.

---

### List GCP Resources by Type

```
GET /resources?resource_type=<type>&project_id=<string>&limit=50&offset=0
```

- `resource_type`: `compute_instance`, `storage_bucket`, or `vpc_network`
- `project_id`: defaults to the platform's configured GCP project

**Response 200**:
```json
{
  "resource_type": "<string>",
  "project_id": "<string>",
  "resources": [
    {
      "resource_name": "<string>",
      "gcp_status": "<string>",
      "zone_or_region": "<string | null>",
      "key_metadata": "<string>",
      "creation_timestamp": "<ISO 8601 | null>"
    }
  ],
  "total_count": "<int>",
  "queried_at": "<ISO 8601>"
}
```

---

### List My Jobs

```
GET /jobs?status=<filter>&limit=20&offset=0
```

**Query params**:
- `status`: optional filter (`pending`, `in_progress`, `succeeded`, `failed`, `cancelled`)
- `limit`: default 20, max 100
- `offset`: default 0

**Response 200**:
```json
{
  "jobs": [<JobStatus>],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

## Error Response Format

All error responses follow this structure:

```json
{
  "error_code": "<string>",
  "message": "<human-readable string>",
  "details": {},
  "correlation_id": "<UUID | null>",
  "timestamp": "<ISO 8601>"
}
```

### Error Codes

| Code | HTTP Status | Meaning |
|------|------------|---------|
| `VALIDATION_ERROR` | 400 | Request body fails schema validation |
| `GUARDRAIL_VIOLATION` | 403 | Developer request exceeds allowed parameters |
| `RATE_LIMIT_EXCEEDED` | 429 | Developer daily provisioning limit reached |
| `IDEMPOTENCY_CONFLICT` | 409 | Duplicate provisioning request for same resource |
| `UNAUTHORIZED` | 401 | Invalid or expired API key |
| `NOT_FOUND` | 404 | Resource not found |
| `JOB_NOT_CANCELLABLE` | 409 | Job state does not allow cancellation |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
