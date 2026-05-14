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
**Responsibilities**: Query live GCP resource status, format human-readable response, list project resources by type.

### Task Input Schema

`query_type` drives behaviour: `"single"` requires `resource_name`; `"list"` returns all resources of `resource_type` in the project.

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "query_type": "single | list",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string | null>",
  "project_id": "<string>",
  "zone": "<string | null>",
  "region": "<string | null>",
  "requesting_user": "<email>",
  "user_role": "developer | platform_engineer"
}
```

### Task Output Schema — Single Resource Found

`metadata` is typed per `resource_type`. All status strings are GCP API verbatim.

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "found",
  "query_type": "single",
  "resource_type": "<string>",
  "resource_name": "<string>",
  "gcp_status": "<GCP status string>",
  "metadata": "<see typed metadata schemas below>",
  "human_readable_summary": "<string>",
  "queried_at": "<ISO 8601 timestamp>"
}
```

#### Typed Metadata — `compute_instance`

```json
{
  "machine_type": "e2-standard-4",
  "zone": "us-central1-a",
  "network": "projects/my-proj/global/networks/default",
  "subnetwork": "projects/my-proj/regions/us-central1/subnetworks/default",
  "internal_ip": "10.128.0.2",
  "external_ip": "<string | null>",
  "disk_size_gb": 50,
  "creation_timestamp": "<ISO 8601>",
  "labels": {}
}
```

#### Typed Metadata — `storage_bucket`

```json
{
  "storage_class": "STANDARD",
  "location": "US-CENTRAL1",
  "location_type": "region",
  "versioning_enabled": false,
  "uniform_bucket_level_access": true,
  "public_access_prevention": "enforced",
  "creation_time": "<ISO 8601>",
  "labels": {}
}
```

#### Typed Metadata — `vpc_network`

```json
{
  "auto_create_subnetworks": false,
  "routing_mode": "REGIONAL",
  "subnet_count": 2,
  "subnets": [
    {
      "name": "subnet-us-central1",
      "region": "us-central1",
      "cidr": "10.0.0.0/24",
      "private_google_access": true
    }
  ],
  "creation_timestamp": "<ISO 8601>"
}
```

### Task Output Schema — List (query_type = "list")

```json
{
  "correlation_id": "<UUID>",
  "request_id": "<UUID>",
  "status": "listed",
  "query_type": "list",
  "resource_type": "<string>",
  "project_id": "<string>",
  "resources": [
    {
      "resource_name": "<string>",
      "gcp_status": "<GCP status string>",
      "zone_or_region": "<string | null>",
      "key_metadata": "<abbreviated metadata — machine_type or storage_class or routing_mode>"
    }
  ],
  "total_count": "<int>",
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
