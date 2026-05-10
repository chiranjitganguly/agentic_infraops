# A2A Agent Contracts

**Protocol**: Google ADK native A2A
**Version**: 1.0.0 | **Date**: 2026-05-10

All agents expose a `/.well-known/agent.json` agent card and a `/tasks` endpoint implementing the ADK task lifecycle: `submitted → working → completed / failed`.

Every task input and output MUST carry `correlation_id` and `request_id`.

---

## Orchestrator Agent

**Name**: `orchestrator-agent`
**Port**: 8100
**Responsibilities**: Classify intent, enforce guardrails and rate limits, route to sub-agents, manage confirmation flow, handle clarification loop.

### Supported Intents

| Intent | Routes To |
|--------|-----------|
| `provision` | Provisioning Agent |
| `enquiry` | Enquiry Agent |
| `faq` | FAQ Agent |
| `clarify` | Returns clarification question to caller (no sub-agent) |

### Task Input Schema

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "raw_input": "<string>",
  "channel": "chatbot | email",
  "requesting_user": "<email>",
  "user_role": "developer | platform_engineer",
  "email_thread_id": "<string | null>"
}
```

### Task Output Schema

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "outcome": "routed | clarification_needed | rejected | rate_limited | guardrail_violation | expired",
  "intent": "provision | enquiry | faq | null",
  "confidence": "<float 0.0–1.0 | null>",
  "clarification_question": "<string | null>",
  "rejection_reason": "<string | null>",
  "sub_agent_result": "<sub-agent output object | null>"
}
```

### Orchestrator Rules

- If `confidence < 0.7`: set `outcome = clarification_needed`, return top 2 candidate intents as `clarification_question`
- If `user_role = developer` and `resource_type = vpc_network`: set `outcome = guardrail_violation`
- If `user_role = developer` and `daily_count >= 10`: set `outcome = rate_limited`
- If confirmation not received within 20 minutes: set `outcome = expired`, cancel pending job

---

## Provisioning Agent

**Name**: `provisioning-agent`
**Port**: 8101
**Responsibilities**: Validate parameters, enforce idempotency, generate confirmation summary, publish to PubSub, track job state.

### Task Input Schema

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "infra_request_id": "<UUID>",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string>",
  "region": "<string>",
  "zone": "<string | null>",
  "parameters": "<resource-type-specific parameter object>",
  "requesting_user": "<email>",
  "user_role": "developer | platform_engineer",
  "confirmed": false
}
```

### Task Output Schema — Pre-Confirmation (Confirmation Summary)

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "job_id": "<UUID>",
  "status": "awaiting_confirmation",
  "confirmation_summary": "<human-readable string describing what will be created>",
  "idempotency_key": "<string>",
  "existing_job": "<ProvisioningJob object | null>",
  "expires_at": "<ISO 8601 timestamp>"
}
```

### Task Output Schema — Post-Confirmation (Job Queued)

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "job_id": "<UUID>",
  "status": "pending",
  "message": "Provisioning job queued. Track progress at /api/v1/jobs/{job_id}/stream"
}
```

### Task Output Schema — Error

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "error",
  "error_code": "VALIDATION_ERROR | IDEMPOTENCY_CONFLICT | GUARDRAIL_VIOLATION | RATE_LIMIT_EXCEEDED",
  "error_message": "<human-readable string>",
  "invalid_fields": ["<field_name>"]
}
```

### Parameter Schemas by Resource Type

**compute_instance**:
```json
{
  "machine_type": "<string, e.g. e2-standard-4>",
  "disk_size_gb": "<integer, default 50>",
  "image_family": "<string, default debian-12>",
  "image_project": "<string, default debian-cloud>",
  "network": "<string, default default>",
  "tags": ["<string>"]
}
```

**storage_bucket**:
```json
{
  "storage_class": "STANDARD | NEARLINE | COLDLINE | ARCHIVE",
  "uniform_bucket_level_access": "<boolean, default true>",
  "versioning_enabled": "<boolean, default false>",
  "labels": {"<key>": "<value>"}
}
```

**vpc_network** (platform_engineer only):
```json
{
  "auto_create_subnetworks": "<boolean, default false>",
  "subnet_name": "<string>",
  "subnet_region": "<string>",
  "subnet_cidr": "<string, e.g. 10.0.0.0/24>"
}
```

---

## Enquiry Agent

**Name**: `enquiry-agent`
**Port**: 8102
**Responsibilities**: Query live GCP resource status, format human-readable response.

### Task Input Schema

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string>",
  "project_id": "<string>",
  "zone": "<string | null>",
  "region": "<string | null>",
  "requesting_user": "<email>",
  "user_role": "developer | platform_engineer"
}
```

### Task Output Schema — Success

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "found",
  "resource_type": "<string>",
  "resource_name": "<string>",
  "gcp_status": "<GCP status string>",
  "metadata": "<resource-type-specific metadata object>",
  "human_readable_summary": "<string>",
  "queried_at": "<ISO 8601 timestamp>"
}
```

### Task Output Schema — Not Found

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "not_found",
  "resource_type": "<string>",
  "resource_name": "<string>",
  "message": "No resource named '{resource_name}' of type '{resource_type}' found in project '{project_id}'."
}
```

### Task Output Schema — Access Denied

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "access_denied",
  "message": "You do not have permission to view this resource."
}
```

---

## FAQ Agent

**Name**: `faq-agent`
**Port**: 8103
**Responsibilities**: Hybrid document retrieval, answer synthesis, source citation.

### Task Input Schema

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "question": "<string>",
  "requesting_user": "<email>",
  "max_chunks": 5
}
```

### Task Output Schema — Answer Found

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "answered",
  "answer": "<synthesised answer string>",
  "sources": [
    {
      "document_title": "<string>",
      "document_url": "<string | null>",
      "chunk_excerpt": "<string, first 200 chars of matched chunk>",
      "relevance_score": "<float>"
    }
  ],
  "confidence": "<float 0.0–1.0 | null>",
  "answered_at": "<ISO 8601 timestamp>"
}
```

### Task Output Schema — No Results

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "no_results",
  "message": "No relevant documentation found for your question. Consider checking the GCP documentation directly or contacting the platform engineering team.",
  "answered_at": "<ISO 8601 timestamp>"
}
```
