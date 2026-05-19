# Agentic InfraOps Platform — Technical Documentation

**Version**: 1.0  
**Last Updated**: 2026-05-18  
**Repository**: `agentic_infraops`

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Request Flows](#3-request-flows)
   - 3.1 [VM Provisioning (Web UI)](#31-vm-provisioning-web-ui)
   - 3.2 [Resource Status Enquiry](#32-resource-status-enquiry)
   - 3.3 [FAQ Query](#33-faq-query)
   - 3.4 [Email-Triggered Provisioning](#34-email-triggered-provisioning)
4. [Module Reference](#4-module-reference)
   - 4.1 [Agents](#41-agents)
   - 4.2 [MCP Servers](#42-mcp-servers)
   - 4.3 [Business Logic](#43-business-logic)
   - 4.3a [A2A Protocol — Agent-to-Agent Invocation](#43a-a2a-protocol--agent-to-agent-invocation)
   - 4.3b [Correlation Context — Request Tracing](#43b-correlation-context--request-tracing)
   - 4.4 [Contracts (Schemas)](#44-contracts-schemas)
   - 4.5 [Workflows (Airflow DAGs)](#45-workflows-airflow-dags)
   - 4.6 [Web Backend](#46-web-backend)
   - 4.7 [Web Frontend](#47-web-frontend)
   - 4.8 [Infrastructure & Database](#48-infrastructure--database)
   - 4.9 [Observability](#49-observability)
5. [State Machines](#5-state-machines)
6. [Security Model](#6-security-model)
7. [Configuration Reference](#7-configuration-reference)
8. [Service Ports](#8-service-ports)
9. [Architectural Decisions (ADRs)](#9-architectural-decisions-adrs)
10. [Technology Stack](#10-technology-stack)
11. [Local Development](#11-local-development)
12. [Key Design Patterns](#12-key-design-patterns)

---

## 1. Platform Overview

Agentic InfraOps is a **multi-agent, event-driven GCP infrastructure self-service platform**. It enables developers to provision GCP resources (VMs, storage buckets, VPCs), query resource status, and get answers to infrastructure FAQs — all through natural language, either via a React chat UI or email.

### What it does

| Intent | Input | Output |
|--------|-------|--------|
| **Provision** | "Provision a 2 vCPU VM called my-app in us-central1" | Two-phase confirmation → Airflow DAG → GCP resource |
| **Enquiry** | "What is the status of my-app?" | Real-time GCP resource metadata |
| **FAQ** | "What machine types are available?" | LLM-generated answer from knowledge base |

### What makes it unique

- **Natural language input**: No YAML, no CLI — just plain English requests
- **Two-phase confirmation**: Every provisioning request shows a human-readable summary for review before execution
- **Full audit trail**: Every action is logged with correlation IDs and actor information
- **Developer guardrails**: Region, machine type, and daily provisioning caps enforced at the orchestrator level
- **Event-driven execution**: Provisioning is decoupled from the API — PubSub carries the job to Airflow for reliable execution
- **Real-time status**: SSE push from PostgreSQL LISTEN/NOTIFY keeps the UI up to date without polling

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT LAYER                                     │
│    React Chat UI (port 3001)          Gmail / Email Input                   │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ HTTPS / REST + SSE
┌──────────────────────▼──────────────────────────────────────────────────────┐
│                       WEB BACKEND (FastAPI, port 8000)                      │
│  Auth Middleware (JWT + API Key)  │  Routers: /requests /jobs /auth /sse    │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ A2A HTTP
┌──────────────────────▼──────────────────────────────────────────────────────┐
│               ORCHESTRATOR AGENT (Google ADK, port 8001)                    │
│  Intent Classification  │  Guardrails  │  Rate Limiting  │  Routing         │
└──────┬─────────────────┬────────────────────────┬────────────────────────────┘
       │ A2A HTTP        │ A2A HTTP               │ A2A HTTP
┌──────▼──────┐  ┌───────▼────────┐  ┌──────────▼─────────┐
│ PROVISIONING│  │ ENQUIRY AGENT  │  │    FAQ AGENT       │
│ AGENT       │  │ (port 8003)    │  │    (port 8004)     │
│ (port 8002) │  └───────┬────────┘  └──────────┬─────────┘
└──────┬──────┘          │                       │
       │ PubSub Publish  │ GCP API               │ Qdrant Search + LiteLLM
       │                 │                       │
┌──────▼──────┐  ┌───────▼────────┐  ┌──────────▼─────────┐
│  GCP PUBSUB │  │  mcp-gcp-      │  │  mcp-knowledge-    │
│  EMULATOR   │  │  resource      │  │  base (port 8093)  │
│  (port 8085)│  │  (port 8090)   │  └────────────────────┘
└──────┬──────┘  └────────────────┘
       │ PubSubPullSensor
┌──────▼──────────────────────────────────────────────────────────────────────┐
│                     APACHE AIRFLOW (port 8080)                              │
│  provision_vm_dag: wait_for_message → dry_run → provision → backstage →    │
│                    update_succeeded (or rollback_vm → update_failed)        │
└──────┬──────────────────────────────────────────────────────────────────────┘
       │ psycopg2 UPDATE → PostgreSQL TRIGGER → pg_notify
┌──────▼──────────────────────────────────────────────────────────────────────┐
│              POSTGRESQL 15 (port 5432)                                      │
│  provisioning_jobs │ infra_requests │ user_roles │ audit_events             │
│  TRIGGER: AFTER UPDATE OF status → pg_notify('infraops_job_status', ...)   │
└──────┬──────────────────────────────────────────────────────────────────────┘
       │ asyncpg LISTEN
┌──────▼──────────────────────────────────────────────────────────────────────┐
│         WEB BACKEND SSE /jobs/{job_id}/stream                               │
│  Emits current status on connect, then streams NOTIFY events                │
└──────┬──────────────────────────────────────────────────────────────────────┘
       │ SSE (text/event-stream)
       └──→ React UI (useJobStream hook, JobStatusTimeline component)
```

### Supporting Infrastructure

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   LiteLLM   │  │   Qdrant    │  │  Backstage  │  │  Prometheus │
│  (port 4000)│  │  (port 6333)│  │  (port 7007)│  │  (port 9090)│
│ LLM Gateway │  │ Vector DB   │  │  Catalog    │  │  Metrics    │
└─────────────┘  └─────────────┘  └─────────────┘  └──────┬──────┘
                                                            │
                                                   ┌────────▼──────┐
                                                   │   Grafana     │
                                                   │  (port 3000)  │
                                                   └───────────────┘
```

---

## 3. Request Flows

### 3.1 VM Provisioning (Web UI)

This is the primary and most complex flow. It involves two phases: confirmation and execution.

#### Phase 1: Submission and Confirmation

```
User types: "provision a 2 vCPU vm called my-test in us-central1"
         │
         ▼
React UI (useSubmitRequest hook)
  → POST /api/v1/requests  { raw_input: "...", channel: "web" }
         │
         ▼
web-backend AuthMiddleware
  → Validate Bearer JWT (or X-API-Key)
  → Set request.state.user_id = "cg4ai@gmail.com", role = "developer"
         │
         ▼
POST /requests handler (requests.py)
  → Create correlation context (correlation_id, request_id)
  → Call mcp-postgres: create_infra_request()
    * status = "received", expires_at = now + 20 min
  → Call orchestrator-agent A2A HTTP /run
         │
         ▼
orchestrator-agent
  → Deserialize OrchestratorInput from message parts[0].text
  → Call intent_classification skill
    * LiteLLM call → "provision", confidence 0.92
    * Normalized params: { resource_type: "compute_instance",
                           resource_name: "my-test",
                           region: "us-central1",
                           machine_type: "e2-standard-2" }
  → Confidence ≥ 0.55 → proceed
  → Intent = "provision" + role = "developer" → run guardrails
    * validate_provisioning_guardrails():
      - region "us-central1" ∈ ALLOWED_REGIONS ✓
      - machine_type "e2-standard-2" ∈ ALLOWED_MACHINE_TYPES ✓
  → Check daily usage: get_daily_usage_count(user) → 3/10 ✓
  → Route to provisioning-agent A2A HTTP /run
         │
         ▼
provisioning-agent (confirmed=False)
  → Compute idempotency_key = SHA256("compute_instance:my-test:us-central1")
  → Check postgres: get_provisioning_job_by_idempotency_key()
    * Not found → create new job
  → Call postgres: create_provisioning_job()
    * status = "awaiting_confirmation", expires_at = now + 20 min
  → Call confirmation.build_confirmation_summary()
    * Returns human-readable text with machine type, disk, image, cost warning
  → Return ProvisioningConfirmationOutput { job_id, confirmation_summary, expires_at }
         │
         ▼
Back through orchestrator → web-backend → HTTP 202 response:
{
  "infra_request_id": "...",
  "job_id": "fdd2f690-...",
  "intent": "provision",
  "status": "awaiting_confirmation",
  "intent_summary": "You are about to create a Compute Engine VM...",
  "confirmation_summary": "You are about to create...\n  • Name: my-test\n  • Machine: e2-standard-2\n  ...",
  "expires_at": "2026-05-17T03:08:50Z",
  "correlation_id": "...",
  "trace": [{ "agent_name": "orchestrator_agent", ... }, ...]
}
         │
         ▼
React UI renders IntentConfirmationCard:
  • Shows confirmation_summary as formatted text
  • "Looks right, continue" button → triggers confirm flow
  • "Rephrase" button → triggers clarification flow
  • Countdown timer (20-minute deadline)
```

#### Phase 2: Confirmation and Execution

```
User clicks "Looks right, continue"
         │
         ▼
React UI (useJobConfirm hook)
  → POST /api/v1/jobs/fdd2f690-.../confirm
         │
         ▼
web-backend confirm_job handler (jobs.py)
  → Fetch job from postgres (verify owned by user, status=awaiting_confirmation)
  → Re-call provisioning-agent A2A HTTP /run with confirmed=True
         │
         ▼
provisioning-agent (confirmed=True)
  → Call postgres: update_request_status(confirmed_at=now, status="confirmed")
  → Call postgres: update_job_status(status="queued")
  → Publish ProvisioningRequestEvent to PubSub topic:
      infraops.provisioning.requests
      Payload: { job_id, resource_type, resource_name, region, zone,
                 parameters, requesting_user, schema_version="1.0.0" }
  → Trigger Airflow DAG: POST /api/v1/dags/provision_vm_dag/dagRuns
      { dag_run_id: "api__2026-05-17T02:48:57", conf: { job_id } }
  → Emit audit event: request_confirmed
  → Return ProvisioningQueuedOutput { job_id, status="queued" }
         │
         ▼
HTTP 200: { "job_id": "...", "status": "queued",
            "message": "Track progress at /api/v1/jobs/.../stream" }
         │
         ▼
React UI opens SSE stream: GET /api/v1/jobs/fdd2f690-.../stream
  → Backend immediately fetches current DB status ("queued") and emits it
  → Then listens on pg_notify("infraops_job_status") for future updates
```

#### Phase 3: Airflow DAG Execution

```
Airflow DAG: provision_vm_dag
         │
         ▼
Task 1: wait_for_message (PubSubPullSensor)
  → Polls infraops-provisioning-requests-vm-sub every 10s
  → Pulls message, ACKs it, decodes JSON → XCom["message_data"]
         │
         ▼
Task 2: update_in_progress
  → Extract job_data from XCom (job_id, resource_name, region, parameters, ...)
  → psycopg2 UPDATE provisioning_jobs SET status='in_progress' WHERE id=job_id
  → PostgreSQL TRIGGER fires → pg_notify("infraops_job_status", { job_id, status:"in_progress" })
  → SSE stream on web backend receives notify → emits to browser
  → Browser JobStatusTimeline updates: "queued" → "in_progress"
         │
         ▼
Task 3: dry_run_validate
  → Call business_logic.gcp_compute.provisioner.create_vm(dry_run=True)
  → Validates machine_type, disk_size, image family — no GCP API call
  → Raises RuntimeError if validation fails
         │
         ▼
Task 4: provision_vm (retries=3, exponential backoff)
  → Call business_logic.gcp_compute.provisioner.create_vm(dry_run=False)
  → GCP Compute Engine instances.insert() API call
  → Wait for zone operation to complete
  → Append resource to rollback_resources (ADR-0006)
  → XCom push: gcp_resource_id = "4859268277364626431"
         │
         ▼
Task 5: register_backstage
  → Build Backstage entity (apiVersion, kind=Component, metadata, spec)
  → POST to Backstage catalog API via mcp-backstage
  → If BACKSTAGE_REQUIRED=true and fails → raises RuntimeError → triggers rollback
  → If BACKSTAGE_REQUIRED=false and fails → logs warning, continues
         │
         ▼
Task 6: update_succeeded
  → psycopg2 UPDATE provisioning_jobs SET status='succeeded', gcp_resource_id='...'
  → PostgreSQL TRIGGER fires → pg_notify → SSE → browser
  → Browser: JobStatusTimeline shows "succeeded" ✓

ON FAILURE (provision_vm or register_backstage fails):
         │
         ▼
Task: rollback_vm (TriggerRule.ONE_FAILED)
  → For each resource in rollback_resources:
    → Call GCP instances.delete()
    → Ignore 404 (resource may not exist)
         │
         ▼
Task: update_failed (TriggerRule.ALL_SUCCESS on rollback_vm)
  → UPDATE provisioning_jobs SET status='failed', error_message='...'
  → PostgreSQL TRIGGER fires → SSE → browser shows "failed"
```

---

### 3.2 Resource Status Enquiry

```
User types: "what is the status of my-test vm?"
         │
         ▼
POST /api/v1/requests { raw_input: "what is the status of my-test vm?" }
         │
         ▼
orchestrator-agent
  → intent_classification: intent="enquiry", confidence=0.89
  → Normalized: { resource_type: "compute_instance", resource_name: "my-test",
                  query_type: "single", zone: "us-central1-a" }
  → No guardrails for enquiry
  → Route to enquiry-agent
         │
         ▼
enquiry-agent
  → query_type = "single"
  → Call business_logic.status_query.querier.query_resource_status()
    → GCP Compute Engine instances.get() API call
    → Returns: { status: "RUNNING", zone, machine_type, disk_size, external_ip, ... }
  → Fallback: if GCP unavailable → query provisioning_jobs table
  → Call format_status_response() skill:
    → "my-test is RUNNING in us-central1-a (e2-standard-2, 50 GB boot disk)"
  → Emit audit event: status_queried
  → Return EnquiryFoundOutput { resource_type, resource_name, status, metadata, human_readable_summary }
         │
         ▼
HTTP 200:
{
  "intent": "enquiry",
  "query_type": "single",
  "resource_type": "compute_instance",
  "resource_name": "my-test",
  "gcp_status": "RUNNING",
  "human_readable_summary": "my-test is RUNNING in us-central1-a...",
  "metadata": { "machine_type": "e2-standard-2", "external_ip": "34.x.x.x", ... }
}
         │
         ▼
React UI renders EnquiryResultCard with resource metadata table
```

---

### 3.3 FAQ Query

```
User types: "what machine types are available for developers?"
         │
         ▼
POST /api/v1/requests { raw_input: "what machine types are available for developers?" }
         │
         ▼
orchestrator-agent
  → intent_classification: intent="faq", confidence=0.95
  → Route to faq-agent
         │
         ▼
faq-agent
  → Call mcp-knowledge-base search_documents():
    → Embed query via LiteLLM /v1/embeddings (text-embedding-3-small, 1536D)
    → Qdrant hybrid search (dense vector + BM25 sparse, RRF fusion)
    → Returns top-5 chunks from knowledge base docs with scores
  → If no chunks above score_threshold=0.3 → return FAQNoResultsOutput
  → Call LiteLLM /v1/chat/completions:
    → Model: FAQ_GENERATION_MODEL (default gpt-4o-mini)
    → System: ANSWER_PROMPT with context chunks
    → Returns generated answer
  → Call postgres: create_faq_query() — store question + chunks + answer for analytics
  → Emit audit event: faq_answered
  → Return FAQAnsweredOutput { answer, sources }
         │
         ▼
HTTP 200:
{
  "intent": "faq",
  "answer": "For developers, available machine types are:\n• e2-standard-2 (2 vCPU, 8 GB RAM)\n• e2-standard-4...",
  "sources": [{ "doc": "vm-provisioning.md", "chunk": "Machine type constraints..." }]
}
         │
         ▼
React UI renders FAQAnswerCard with markdown-formatted answer + source links
```

---

### 3.4 Email-Triggered Provisioning

```
Developer sends email to infraops@yourcompany.com:
  Subject: "Provision VM"
  Body: "I need a 2 CPU VM called staging-api in us-east1"
         │
         ▼
gmail-poller service (runs every 30s)
  → mcp-gmail: poll_unread_messages()
  → Filters out auto-replies via is_auto_reply()
  → For each new message:
    → mcp-gmail: get_message(message_id)
    → POST /api/v1/requests {
        raw_input: email_body,
        channel: "email",
        email_thread_id: "...",
        email_message_id: "..."
      }
         │
         ▼
[Same flow as Web UI — orchestrator routes to provisioning-agent]
         │
         ▼
On confirmation_needed:
  → Email response: "Please confirm VM provisioning: [summary] — reply 'confirm' or 'cancel'"
         │
         ▼
Developer replies: "confirm"
  → gmail-poller picks up reply
  → POST /api/v1/jobs/{job_id}/confirm (matched by email thread_id)
         │
         ▼
[Same Airflow DAG execution flow]
         │
         ▼
On completion: notification-service
  → Subscribes to PubSub infraops-provisioning-status-sub
  → On ProvisioningStatusEvent with status="succeeded":
    → mcp-gmail: send_email() to requesting user
      Subject: "VM staging-api provisioned successfully"
      Body: "Your VM staging-api (e2-standard-2) in us-east1-b is now RUNNING."
```

---

## 4. Module Reference

### 4.1 Agents

All agents are **stateless** Google ADK `BaseAgent` subclasses. They implement `_run_async_impl()` which receives an `InvocationContext`, deserializes JSON input from `parts[0].text`, executes business logic via **business_logic**, and yields a single `Event` with JSON output in `parts[0].text`.

#### Orchestrator Agent

| Property | Detail |
|----------|--------|
| **File** | `agents/orchestrator/agent.py` |
| **Port** | 8001 |
| **Purpose** | Classification, routing, guardrails, rate limiting |
| **Input** | `OrchestratorInput` — raw_input, channel, requesting_user, user_role, correlation_id, request_id |
| **Output** | `OrchestratorOutput` — outcome, intent, result dict, trace |

**Routing logic** (`route()` function):

```
OrchestratorInput
  │
  ├─ classify(raw_input) via LiteLLM
  │    ↓
  │  confidence < 0.55 ──→ outcome=clarification_needed (web) or rejected (email)
  │
  ├─ intent=provision + role=developer
  │    ├─ validate_provisioning_guardrails() ──→ outcome=guardrail_violation if fails
  │    └─ check daily limit (postgres-mcp) ──→ outcome=rate_limited if 10/10
  │
  └─ Route to sub-agent:
       provision ──→ provisioning-agent A2A call
       enquiry   ──→ enquiry-agent A2A call
       faq       ──→ faq-agent A2A call
```

**Default guardrails** (configurable via env):

| Guardrail | Default Value |
|-----------|---------------|
| ALLOWED_REGIONS | us-central1, us-east1, europe-west1 |
| ALLOWED_MACHINE_TYPES | e2-standard-2, e2-standard-4, e2-standard-8 |
| ALLOWED_STORAGE_CLASSES | STANDARD, NEARLINE |
| DEVELOPER_DAILY_LIMIT | 10 provisioning ops/day |
| VPC for developers | Always blocked |

---

#### Provisioning Agent

| Property | Detail |
|----------|--------|
| **File** | `agents/provisioning/agent.py` |
| **Port** | 8002 |
| **Purpose** | Two-phase idempotent job creation and PubSub publishing |
| **Input** | `ProvisioningInput` — resource_type, resource_name, region, zone, parameters, requesting_user, user_role, confirmed (bool) |
| **Output** | `ProvisioningConfirmationOutput` (phase 1) or `ProvisioningQueuedOutput` (phase 2) |

**Idempotency key** = `SHA256(f"{resource_type}:{resource_name}:{region}")`

**Phase 1 (confirmed=False)**:
1. Compute idempotency key
2. Check for existing job by idempotency key
   - Found + non-terminal status → return existing job state (no duplicate create)
   - Found + awaiting_confirmation → rebuild confirmation summary, return it
   - Found + already queued/in_progress → return ProvisioningQueuedOutput
3. Create new `provisioning_job` row (status=awaiting_confirmation)
4. Build `confirmation_summary` via `build_confirmation_summary()`
5. Return `ProvisioningConfirmationOutput`

**Phase 2 (confirmed=True)**:
1. Update `infra_request` status to "confirmed"
2. Update `provisioning_job` status to "queued"
3. Publish `ProvisioningRequestEvent` to PubSub
4. Trigger Airflow DAG `provision_vm_dag`
5. Emit `request_confirmed` audit event
6. Return `ProvisioningQueuedOutput`

---

#### Enquiry Agent

| Property | Detail |
|----------|--------|
| **File** | `agents/enquiry/agent.py` |
| **Port** | 8003 |
| **Purpose** | GCP resource status lookup — single resource or project-wide list |
| **Input** | `EnquiryInput` — query_type (single/list), resource_type, resource_name, zone, region, project_id |
| **Output** | `EnquiryFoundOutput`, `EnquiryNotFoundOutput`, or `EnquiryListOutput` |

**Query types**:
- `single`: Call GCP API → return status + full metadata
- `list`: Call GCP API → return all matching resources; fall back to provisioning_jobs table if GCP unavailable

Both paths call `format_status_response()` or `format_list_response()` from the status_query skill to produce human-readable summaries. Emits `status_queried` audit event on success.

---

#### FAQ Agent

| Property | Detail |
|----------|--------|
| **File** | `agents/faq/agent.py` |
| **Port** | 8004 |
| **Purpose** | Knowledge base retrieval + LLM answer generation |
| **Input** | `FAQInput` — question, max_chunks (default 5), requesting_user |
| **Output** | `FAQAnsweredOutput` (answer + sources) or `FAQNoResultsOutput` |

**Two-step pipeline**:
1. **Retrieve**: `mcp-knowledge-base.search_documents()` → hybrid BM25 + dense vector search in Qdrant
2. **Generate**: LiteLLM `/v1/chat/completions` with retrieved chunks as context

Stores every query in `faq_queries` table for analytics. Emits `faq_answered` audit event.

---

### 4.2 MCP Servers

MCP (Model Context Protocol) servers are **the sole gateway** to every external system. No agent or DAG may call GCP, PostgreSQL, PubSub, or any external API directly — all calls must pass through an MCP server tool. Each server runs as an independent Docker container, exposes tools via FastMCP (SSE transport), and is wrapped with a circuit breaker.

```
Agent / DAG Task
      │
      ▼  HTTP (SSE transport or direct module import)
  MCP Server  ──→  External System (GCP / Postgres / PubSub / Qdrant / Airflow / Backstage / Gmail)
      │
      └─ All @mcp.tool() functions wrapped with @gcp_circuit_breaker
         (5 consecutive failures → OPEN, 60 s reset, raises CircuitOpenError)
```

**How agents call MCP tools** — two patterns are used:

1. **Direct module import** (same-process): The Airflow DAG tasks and some business_logic modules import the MCP server module directly and call the Python function. E.g., `from mcp_servers.gcp_resource import server; server.create_vm(...)`.
2. **HTTP SSE transport**: Agents running in separate containers call tools over the MCP SSE protocol at the server's port. FastMCP handles routing to the correct tool function.

---

#### mcp-postgres (`mcp_servers/postgres/server.py`, port 8089)

The authoritative persistent state store. Wraps all SQL operations so no component ever writes raw SQL except through these tools.

**Tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `create_provisioning_job` | `(job_data: dict) → dict` | INSERTs a row in `provisioning_jobs` with `status='awaiting_confirmation'`. Returns full row. |
| `get_provisioning_job` | `(job_id: str) → dict \| None` | Fetches job by UUID. Returns `None` if not found. |
| `get_provisioning_job_by_idempotency_key` | `(idempotency_key: str) → dict \| None` | Deduplication check — used in Phase 1 of provisioning to detect repeat requests. |
| `update_job_status` | `(job_id, status, gcp_resource_id?, error_message?, rollback_resources?) → dict` | Updates status + optional fields. Calls `SELECT pg_notify('infraops_job_status', ...)` explicitly after UPDATE so SSE subscribers receive push even if no DB trigger is configured. Appends to (not replaces) `rollback_resources`. |
| `cancel_job` | `(job_id, requesting_user) → dict` | Atomic guard: only matches rows where `status IN ('awaiting_confirmation','queued')` AND `requesting_user=$2`. Returns `{cancelled: true/false}`. |
| `create_infra_request` | `(request_data: dict) → dict` | Inserts into `infra_requests`. Sets `status='pending'`, records `channel` and `raw_input`. |
| `update_request_status` | `(infra_request_id, status, confirmed_at?, confirmed_params?) → dict` | Updates request state; used by provisioning agent when user confirms. |
| `get_user_role` | `(user_id: str) → dict \| None` | Returns `{role, api_key_hash, api_key_expires_at}`. Used by AuthMiddleware. |
| `verify_password` | `(user_id, password) → bool` | bcrypt password check. **Not an `@mcp.tool`** — called internally by `AuthMiddleware`. |
| `verify_api_key` | `(user_id, api_key) → bool` | bcrypt API key check. Checks expiry timestamp. |
| `get_daily_usage_count` | `(requesting_user: str) → dict` | Returns `{count, daily_limit}` for today's UTC date. |
| `increment_daily_usage` | `(requesting_user, daily_limit) → dict` | UPSERT on `(requesting_user, date)`. Returns `{limit_reached: bool}`. Blocks if count ≥ daily_limit before incrementing. |
| `create_audit_event` | `(event_data: dict) → dict` | Inserts into `audit_events`. Swallows DB errors — audit must never block the main flow. |
| `create_faq_query` | `(query_data: dict) → dict` | Stores question, retrieved chunks (JSON), and generated answer for analytics. |
| `list_provisioning_jobs` | `(requesting_user, limit?, offset?, status?) → list[dict]` | Paginated job list scoped to the requesting user. |
| `rotate_api_key` | `(user_id, new_key_hash, expires_at) → dict` | Replaces `api_key_hash` and updates expiry. |

**Internal helpers (non-tools):**
- `_parse_job_row(row)` — maps asyncpg `Record` → `dict` with correct types, including `UUID → str` conversion and `rollback_resources` JSON parse.
- `_notify_job_status(conn, job_id, status)` — executes the `pg_notify` call after every status update.

---

#### mcp-pubsub (`mcp_servers/pubsub/server.py`, port 8091)

Wraps Google Cloud PubSub. Supports local emulator via `PUBSUB_EMULATOR_HOST` env var. Uses a lazy singleton publisher (created on first publish call).

**Schema validation**: All three publish tools validate `schema_version == "1.0.0"` before publishing and raise `ValueError` if the version does not match. This enforces the additive-only contract change policy.

**Tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `publish_provisioning_request` | `(event: dict) → dict` | Validates schema_version. Serialises to JSON. Publishes to `infraops.provisioning.requests`. Returns `{message_id}`. |
| `publish_status_event` | `(event: dict) → dict` | Validates schema_version. Publishes to `infraops.provisioning.status`. Returns `{message_id}`. |
| `publish_audit_event` | `(event: dict) → dict` | Validates schema_version. Publishes to `infraops.audit.events`. Returns `{message_id}`. |

**Internal helpers:**
- `_get_publisher()` — lazy singleton `pubsub_v1.PublisherClient`. If `PUBSUB_EMULATOR_HOST` is set, creates client with `api_endpoint` pointing to the emulator.
- `_ensure_topics_exist()` — no-op in production; creates topics in emulator mode if they don't exist.

**Topic → Subscription mapping:**

| Topic | Subscription | Consumer |
|-------|-------------|---------|
| `infraops.provisioning.requests` | `infraops-provisioning-requests-vm-sub` | Airflow `PubSubPullSensor` |
| `infraops.provisioning.status` | `infraops-provisioning-status-sub` | `notification-service` |
| `infraops.audit.events` | `infraops-audit-events-sub` | Audit processor |

---

#### mcp-gcp-resource (`mcp_servers/gcp_resource/server.py`, port 8090)

The only component allowed to call GCP Compute Engine, Cloud Storage, and VPC APIs. All tools decorated with `@gcp_circuit_breaker` (5 failures → OPEN, 60 s auto-reset).

**Lazy singletons**: `_get_compute()` and `_get_storage()` build the GCP API clients on first call using `google-api-python-client` and `google-cloud-storage` respectively.

**VM tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `get_vm_status` | `(project_id, zone, instance_name) → dict` | Calls `compute.instances().get()`. Extracts machine type (last segment of URL), disk size from boot disk, internal IP from `networkInterfaces[0]`, external IP from `accessConfigs[0].natIP`. Returns `NOT_FOUND` dict on 404. |
| `create_vm` | `(project_id, zone, instance_name, machine_type, disk_size_gb, image_family, image_project, network, tags, dry_run) → dict` | Validates `10 ≤ disk_size_gb ≤ 2000`. On `dry_run=True` returns `{status: "DRY_RUN_OK"}` immediately. Otherwise builds instance body, calls `instances().insert()`, polls `_wait_for_zone_operation()` (2 s poll loop), fetches the created instance to get its `id`. Returns `{resource_id, status: "RUNNING"}`. |
| `delete_vm` | `(project_id, zone, instance_name) → dict` | Calls `instances().delete()`, waits for operation. Returns `{status: "DELETED"}`. 404 is silently ignored → `{status: "NOT_FOUND"}` (idempotent rollback). |

**Bucket tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `get_bucket_status` | `(project_id, bucket_name) → dict` | Calls `storage.get_bucket()`. Returns storage class, location, versioning state, IAM config (uniform access, public access prevention). Returns `NOT_FOUND` on 404. |
| `create_bucket` | `(project_id, bucket_name, region, storage_class, uniform_bucket_level_access, versioning_enabled, labels, dry_run) → dict` | On `dry_run=True` returns `{status: "DRY_RUN_OK"}`. Otherwise calls `storage.create_bucket()` with location=region. If `versioning_enabled`, calls `bucket.patch()` in a second API call. Returns `{resource_id: "gs://{bucket_name}", status: "ACTIVE"}`. |
| `delete_bucket` | `(project_id, bucket_name) → dict` | `bucket.delete(force=True)`. Returns `NOT_FOUND` on error containing "404" or "does not exist". |

**VPC tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `get_vpc_status` | `(project_id, network_name) → dict` | Fetches network + iterates `subnetworks[]` refs, fetching each subnet to build `{name, region, cidr, private_google_access}` list. Returns auto_create_subnetworks, routing_mode, subnet_count. |
| `create_vpc_network` | `(project_id, network_name, auto_create_subnetworks, dry_run) → dict` | Calls `networks().insert()`, waits via `_wait_for_global_operation()`. |
| `create_subnetwork` | `(project_id, region, subnet_name, network_name, ip_cidr_range, dry_run) → dict` | Calls `subnetworks().insert()` with `privateIpGoogleAccess=True`. Waits via `_wait_for_region_operation()`. |
| `delete_vpc_network` | `(project_id, network_name) → dict` | Calls `networks().delete()`. 404 → `NOT_FOUND`. |
| `list_project_resources` | `(project_id, resource_type) → list[dict]` | Dispatches to `_list_vms()` (aggregatedList across all zones), `_list_buckets()`, or `_list_vpcs()`. Returns list of `{resource_name, resource_type, gcp_status, zone_or_region, key_metadata, creation_timestamp}`. |

**Operation waiters (internal):**
- `_wait_for_zone_operation(compute, project_id, zone, operation_name)` — polls `zoneOperations().get()` every 2 seconds until `status == "DONE"`. Raises `RuntimeError` if `"error"` key present.
- `_wait_for_region_operation(...)` — same for regional operations.
- `_wait_for_global_operation(...)` — same for global operations.

---

#### mcp-knowledge-base (`mcp_servers/knowledge_base/server.py`, port 8093)

Wraps Qdrant for FAQ document storage and hybrid retrieval. Uses `text-embedding-3-small` (1536D) via LiteLLM for dense vectors and BM25 for sparse vectors.

**Collection**: `infraops_knowledge_base`, cosine distance, dense vectors dim=1536.

**Tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `search_documents` | `(query, top_k=5, score_threshold=0.5) → list[dict]` | Embeds query via LiteLLM → dense search in Qdrant. Returns `[{chunk_text, source_doc, bm25_score, vector_score, final_score, chunk_id}]`. Chunks below `score_threshold` excluded. Note: current implementation is **dense-only** (BM25 field is 0.0; full hybrid pending). |
| `index_document` | `(title, url, content, metadata) → dict` | Splits `content` into 500-word chunks with 50-word overlap. Embeds each chunk. UPSERTs into Qdrant with `chunk_id = UUID(sha256(url + chunk_index))` for idempotency. Returns `{chunks_indexed}`. |
| `get_document_by_id` | `(chunk_id: str) → dict \| None` | Fetches single Qdrant point by UUID. Returns `None` if not found. |
| `get_collection_stats` | `() → dict` | Returns `{vectors_count, indexed_vectors_count, status}` from Qdrant collection info. |

**Custom HTTP route** (non-tool):
```
POST /search  →  search_documents() wrapper
```
Used by the faq-agent when making direct HTTP calls to the knowledge-base MCP server instead of going through the MCP tool protocol.

---

#### mcp-airflow (`mcp_servers/airflow/server.py`, port 8094)

Wraps the Airflow REST API (v1). Authenticates with HTTP Basic Auth (`AIRFLOW_USERNAME` / `AIRFLOW_PASSWORD`).

**Tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `get_dag_run_status` | `(dag_id, dag_run_id) → dict` | GET `/dags/{dag_id}/dagRuns/{dag_run_id}` + GET `.../taskInstances`. Returns `{dag_id, dag_run_id, state, start_date, end_date, task_instances: [{task_id, state, start_date, end_date, try_number}]}`. |
| `list_dag_runs` | `(dag_id, limit=10) → list[dict]` | GET `/dags/{dag_id}/dagRuns` with `order_by=-execution_date`. |
| `get_task_instance` | `(dag_id, dag_run_id, task_id) → dict` | GET `.../taskInstances/{task_id}`. Returns state, duration, try_number, operator. |

**Non-tool function (called directly by provisioning agent):**
```python
trigger_dag_run(dag_id: str, conf: dict | None = None) → dict
```
- Builds `dag_run_id = f"api__{ISO_UTC_timestamp}"`.
- POST `/dags/{dag_id}/dagRuns` with `{dag_run_id, conf}`.
- Returns `{dag_run_id, state}`.
- **Not decorated as `@mcp.tool`** — the provisioning agent calls it via direct Python import, not through the MCP protocol. This is intentional: Airflow triggering is fire-and-forget; a failed Airflow trigger is non-fatal because the PubSub message is already published.

---

#### mcp-backstage (`mcp_servers/backstage/server.py`, port 8096)

Wraps the Backstage catalog REST API. Uses Bearer token auth (`BACKSTAGE_API_TOKEN`). All tools wrapped with `@gcp_circuit_breaker` (same decorator, reused for non-GCP external APIs).

**Tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `register_entity` | `(kind, name, namespace, metadata, spec) → dict` | POST to `/api/catalog/entities` with full Backstage entity body (`apiVersion: backstage.io/v1alpha1`). Returns `{entity_ref}` in format `"kind:namespace/name"`. |
| `update_entity` | `(entity_ref, metadata_patch) → dict` | GET current entity → merge `metadata_patch` into `entity.metadata` → PUT back. Parses `entity_ref` by splitting on `:` and `/`. |
| `get_entity` | `(entity_ref) → dict` | GET by name. Returns `{}` on 404 (not an error — callers check for empty dict). |
| `list_entities_by_owner` | `(owner, kind?) → list[dict]` | GET `/api/catalog/entities?filter=spec.owner={owner}[,kind={kind}]`. |

**Internal helpers:**
- `_entity_ref(kind, namespace, name) → str` — builds the `"kind:namespace/name"` string.
- `_headers() → dict` — builds `Authorization: Bearer {token}` + `Content-Type: application/json`.

---

#### mcp-gmail (`mcp_servers/gmail/server.py`, port 8095)

Wraps the Gmail API via OAuth2 credentials file (`GMAIL_CREDENTIALS_PATH`).

**Tools:**

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `poll_unread_messages` | `(history_id?) → list[dict]` | Lists unread messages in INBOX. If `history_id` provided, uses `history.list()` for incremental poll; otherwise falls back to `messages.list(q="is:unread")`. |
| `get_message` | `(message_id) → dict` | Fetches full message with `format=full`. Decodes base64 body. Returns `{id, thread_id, subject, from, to, body, date}`. |
| `get_thread_messages` | `(thread_id) → list[dict]` | Fetches all messages in a thread, newest first. |
| `send_email` | `(to, subject, body_html, thread_id?) → dict` | Encodes MIME message, base64url-encodes it. If `thread_id` provided, sets `threadId` for reply threading. Calls `messages.send()`. Returns `{message_id, thread_id}`. |
| `mark_as_read` | `(message_id) → dict` | Calls `messages.modify()` with `removeLabelIds=["UNREAD"]`. |
| `is_auto_reply` | `(message_id) → bool` | Checks headers `Auto-Submitted`, `X-Auto-Reply-Type`, `Precedence: bulk/auto_reply`. Returns `True` if any match — used to suppress infinite loops. |

---

### 4.3 Business Logic

The `business_logic/` directory is the **sole location for domain logic** (ADR-0001). Agents and DAG tasks must not contain provisioning, validation, or formatting logic directly — they delegate to modules here. All modules are **stateless**, accept dependencies as Protocol interfaces (injectable for testing), and are independently testable without running agents or external services.

```
Agent / DAG Task
       │
       ▼  direct Python call
  business_logic module
       │
       ▼  Protocol interface (injectable client)
   MCP Server  ──→  External System
```

**Protocol-based dependency injection** — every module defines its external dependencies as `Protocol` classes (structural typing). In production, MCP server module references are passed in. In tests, mock implementations satisfying the Protocol are used. No mocking frameworks needed.

---

#### `business_logic/intent_classification/classifier.py`

Single-pass NL → structured intent + GCP parameters classification using LiteLLM function-calling.

**Public API:**

```python
async def classify(raw_input: str, channel: ChannelType | str) -> ClassificationResult
```

**Logic:**
1. Reads `LITELLM_GATEWAY_URL`, `LITELLM_MASTER_KEY`, `INTENT_CLASSIFICATION_MODEL` from env.
2. Builds a `messages` list with the `_SYSTEM_PROMPT` and user input. If `channel == "email"`, appends a tone hint ("this request came via email").
3. Calls `litellm.acompletion()` with `tool_choice={"type":"function","function":{"name":"classify_intent"}}` (forced tool call — no free-text response accepted). `temperature=0.0`.
4. Extracts `tool_calls[0].function.arguments`, parses JSON.
5. Calls `_build_normalized(intent, raw_input, args)` to produce a typed payload.
6. Records duration metric via `intent_classification_duration_seconds.labels(channel=...).time()`.

**`_CLASSIFY_TOOL` schema** defines the structured output shape:
- `intent`: enum `"provision" | "enquiry" | "faq"`
- `confidence`: float 0–1 (< 0.7 signals ambiguous parameters)
- GCP fields: `resource_type`, `resource_name`, `region`, `zone`, `machine_type`, `disk_size_gb`, `image_family`, `image_project`, `network`, `tags`, `storage_class`, `versioning_enabled`, `subnet_name`, `subnet_cidr`, `project_id`

**`_build_normalized(intent, raw_input, args) → NormalizedPayload | None`:**
- `provision + compute_instance` → `NormalizedVMRequest` (defaults: machine_type=e2-standard-4, disk_size_gb=50, image_family=debian-12, region=us-central1)
- `provision + storage_bucket` → `NormalizedBucketRequest` (defaults: storage_class=STANDARD, versioning_enabled=False)
- `provision + vpc_network` → `NormalizedVPCRequest` (defaults: subnet_cidr=10.0.0.0/24, auto_create_subnetworks=False)
- `enquiry` → `NormalizedEnquiryRequest` with `query_type="list"` if `resource_name` absent, else `"single"`
- `faq` → `NormalizedFAQRequest(question=raw_input)`

**Return types:**

| Type | Fields |
|------|--------|
| `ClassificationResult` | `intent: str`, `confidence: float`, `normalized: NormalizedPayload \| None` |
| `NormalizedVMRequest` | `resource_type`, `resource_name`, `region`, `zone`, `machine_type`, `disk_size_gb`, `image_family`, `image_project`, `network`, `tags`. Method: `as_parameters() → dict` (returns the subset passed to `ProvisioningInput.parameters`). |
| `NormalizedBucketRequest` | `resource_type`, `resource_name`, `region`, `storage_class`, `versioning_enabled`. Method: `as_parameters() → dict`. |
| `NormalizedVPCRequest` | `resource_type`, `resource_name`, `region`, `subnet_name`, `subnet_cidr`, `auto_create_subnetworks`. Method: `as_parameters() → dict`. |
| `NormalizedEnquiryRequest` | `query_type`, `resource_type`, `resource_name`, `project_id`, `zone`, `region` |
| `NormalizedFAQRequest` | `question: str` |

---

#### `business_logic/gcp_compute/guardrails.py`

Policy enforcement for provisioning requests. Three public functions:

**`validate_developer_guardrails(params, region, user_role, guardrails) → GuardrailResult`**
- Accepts `VMParameters` + `DeveloperGuardrails` (allowed lists).
- `platform_engineer` role → always passes immediately.
- Checks `region not in guardrails.allowed_regions` and `params.machine_type not in guardrails.allowed_machine_types`.
- Returns all violations in a single pass (not short-circuit).

**`validate_vpc_guardrail(user_role) → GuardrailResult`**
- `developer` role → always fails with violation `{field:"resource_type", provided:"vpc_network", allowed:["compute_instance","storage_bucket"]}`.
- `platform_engineer` → passes.

**`validate_provisioning_guardrails(resource_type, region, user_role, guardrails, machine_type?, storage_class?) → GuardrailResult`**
- Unified entry point used by the orchestrator for all resource types.
- `platform_engineer` → passes immediately.
- `vpc_network` requested by developer → immediate block.
- For `compute_instance`: checks region + machine_type.
- For `storage_bucket`: checks region + storage_class.
- Returns `GuardrailResult(passed=not violations, violations=[GuardrailViolation(field, provided, allowed)])`.

---

#### `business_logic/gcp_compute/provisioner.py`

Core VM creation logic with dry-run and rollback tracking.

**`async create_vm(params, region, resource_name, zone, project_id, job_id, dry_run, gcp_client, postgres_client) → ProvisionResult`**

- `dry_run=True`: Logs and immediately returns `ProvisionResult(success=True)`. No GCP call. No rollback entry. (Per ADR-0006: never pre-populate rollback from dry-run.)
- `dry_run=False`:
  1. Calls `gcp_client.create_vm(...)` with all parameters from `VMParameters`.
  2. On `CircuitOpenError`: returns `ProvisionResult(success=False, error_message="GCP API circuit breaker open: ...")`.
  3. On any other exception: returns `ProvisionResult(success=False, error_message=str(exc))`.
  4. On success: calls `postgres_client.update_job_status(job_id, rollback_resources=[{type, name, region, zone, gcp_resource_id}])` — rollback entry is appended **before** returning, ensuring the DAG can roll back even if a subsequent step fails.
  5. Returns `ProvisionResult(success=True, gcp_resource_id=response["resource_id"])`.

**Protocols defined in this module:**
- `GcpResourceClient` — requires `create_vm(project_id, zone, instance_name, machine_type, disk_size_gb, image_family, image_project, network, tags, dry_run) → dict`
- `PostgresClient` — requires `update_job_status(job_id, rollback_resources) → None`

---

#### `business_logic/gcp_compute/rollback.py`

Deletes all VMs recorded in `rollback_resources` (idempotent).

**`async rollback_vm(rollback_resources, project_id, gcp_client) → RollbackResult`**

- Filters `rollback_resources` to only `resource_type == "compute_instance"`.
- For each: derives `zone = resource.zone or f"{resource.region}-a"`.
- Calls `gcp_client.delete_vm(project_id, zone, resource.name)`.
- `NOT_FOUND` responses are treated as success (idempotent — resource may never have been created or was already cleaned up).
- Collects `RollbackAttempt(resource_name, zone, status, error?)` per resource.
- Returns `RollbackResult(success=all_deleted, attempts=[...])`.
- `RollbackResult.all_deleted` property: `True` if all attempts have `status in {"DELETED","NOT_FOUND"}`.

---

#### `business_logic/status_query/querier.py`

Live GCP status retrieval. Two public functions:

**`query_resource_status(resource_type, resource_name, project_id, zone?, region?, gcp_client?) → dict`**
- Dispatches to `mcp.get_vm_status()` (requires `zone`), `mcp.get_bucket_status()`, or `mcp.get_vpc_status()` based on `resource_type`.
- If `gcp_status == "NOT_FOUND"`: returns `{not_found: True, resource_name, resource_type}`.
- Otherwise: calls `_parse_metadata(resource_type, raw["metadata"])` to build typed metadata object.
- Returns `{resource_type, resource_name, gcp_status, metadata: VMMetadata|BucketMetadata|VPCMetadata, queried_at: datetime}`.

**`list_resources(resource_type, project_id, gcp_client?) → list[ResourceSummary]`**
- Calls `mcp.list_project_resources(project_id, resource_type.value)`.
- Maps each dict to `ResourceSummary(resource_name, resource_type, gcp_status, zone_or_region, key_metadata, creation_timestamp)`.

**`_parse_metadata(resource_type, raw) → VMMetadata | BucketMetadata | VPCMetadata`**

| Input | Typed output |
|-------|-------------|
| `compute_instance` | `VMMetadata(machine_type, zone, network, subnetwork, internal_ip, external_ip, disk_size_gb, creation_timestamp, labels)` |
| `storage_bucket` | `BucketMetadata(storage_class, location, location_type, versioning_enabled, uniform_bucket_level_access, public_access_prevention, creation_time, labels)` |
| `vpc_network` | `VPCMetadata(auto_create_subnetworks, routing_mode, subnet_count, subnets: list[SubnetSummary], creation_timestamp)` |

**`_default_gcp_client()`** — imports `mcp_servers.gcp_resource.server` and returns the module as a client. Used in production; tests inject a mock implementing `GcpResourceClient` Protocol.

---

#### `business_logic/status_query/formatter.py`

Converts typed GCP metadata objects to human-readable strings.

**`format_status_response(metadata, gcp_status, resource_name, resource_type, project_id="") → str`**

| Resource type | Output format |
|--------------|---------------|
| `compute_instance` | `"{name} is {status} in {zone} ({machine_type}, {disk_size_gb} GB boot disk[, external IP {ip}])[project: {id}]."` |
| `storage_bucket` | `"{name} is {status} in {location} ({storage_class}, versioning on/off)[project: {id}]."` |
| `vpc_network` | `"{name} is {status} with {n} subnet(s), routing mode {mode}[project: {id}]."` |

**`format_list_response(resources, resource_type, project_id="") → str`**
- Empty list → `"No {type}s found[ in project '{id}']."`.
- Otherwise: header line `"Found N {type}(s)[ in project '{id}']:"` + bullet per resource: `"  • {name}[ zone/region] — {status} ({key_metadata})"`.

---

#### `business_logic/document_retrieval/retriever.py`

Retrieves relevant document chunks from the knowledge base.

**`retrieve(question, top_k=5, kb_client?) → list[RetrievedChunk]`**
- Calls `kb_client.search_documents(query=question, top_k=top_k, score_threshold=0.5)`.
- On any exception: logs warning and returns `[]` (never propagates retrieval failures to FAQ agent).
- Filters out results with empty `chunk_text`.
- Returns `[RetrievedChunk(chunk_text, source_doc, bm25_score, vector_score, final_score, chunk_id)]`.

**`_SCORE_THRESHOLD = 0.5`** — applied server-side in mcp-knowledge-base.

---

#### `business_logic/document_retrieval/answer_generator.py`

Generates a cited LLM answer from retrieved chunks.

**`generate_answer(question, chunks) → FAQAnswerResult`**
- Empty chunks → returns `FAQAnswerResult(answer=_FALLBACK_ANSWER, sources_cited=[], confidence=0.0)` immediately.
- Builds context string: chunks formatted as `"[Source: {source_doc}]\n{chunk_text}"` separated by `"---"`.
- Calls `litellm.completion()` (synchronous) with `model=FAQ_GENERATION_MODEL` (default `gpt-4o-mini`), `max_tokens=512`, `temperature=0.2`.
- System prompt constrains the LLM to: answer only from provided context, cite sources by `source_doc` name, stay concise (2-5 sentences), say "I don't know" rather than fabricating.
- On LLM exception: logs error, returns fallback answer.
- Returns `FAQAnswerResult(answer, sources_cited=list({c.source_doc for c in chunks}), confidence=max(c.final_score for c in chunks))`.

**`_FALLBACK_ANSWER`** = "I was unable to generate an answer at this time. Please try again or contact the platform engineering team."

---

#### `business_logic/gcp_network/provisioner.py` and `business_logic/gcp_storage/`

Structural analogues of `gcp_compute/provisioner.py` for VPC and bucket provisioning. Follow the identical pattern:
- `dry_run=True` → validate only, return success, no external call.
- `dry_run=False` → call GCP via `gcp_client`, append to `rollback_resources` on success, catch `CircuitOpenError`.
- Protocol interfaces: `GcpResourceClient` + `PostgresClient`.
- Rollback modules (`gcp_network/rollback.py`) follow the same idempotent-delete-with-NOT_FOUND-ignored pattern as `gcp_compute/rollback.py`.

---

### 4.3a A2A Protocol — Agent-to-Agent Invocation

Agents communicate using **Google ADK's A2A (Agent-to-Agent) HTTP protocol**. The web backend calls the orchestrator; the orchestrator calls sub-agents. All calls are HTTP POST using the ADK `/run` endpoint.

#### ADK Server Setup

Each agent is served by a FastAPI application created with `google.adk.cli.fast_api.get_fast_api_app()`:

```python
app = get_fast_api_app(
    agents_dir=agents_dir,   # parent directory of the agent package
    web=False,               # no ADK web UI
    a2a=True,                # expose /run and session endpoints
    host="0.0.0.0",
    port=port,
    allow_origins=["*"],
)
```

This mounts two routes under `/apps/{app_name}/`:
- `POST /apps/{app_name}/users/{user_id}/sessions/{session_id}` — create/reset a session
- `POST /run` — send a message to the agent and receive streaming events

The `app_name` is derived from the service hostname: `http://provisioning-agent:8002` → `"provisioning"`.

#### A2A Call Sequence (`_call_sub_agent`)

```python
async def _call_sub_agent(agent_url: str, task_data: dict) → dict:
```

**Step 1 — Inject correlation headers:**
```python
headers = {}
inject_correlation_headers(headers)
# Adds: X-Correlation-ID: <uuid>, X-Request-ID: <uuid>
```

**Step 2 — Create a fresh ADK session:**
```python
session_id = str(uuid.uuid4())   # unique per call
POST {agent_url}/apps/{app_name}/users/orchestrator/sessions/{session_id}
body: {}
headers: {X-Correlation-ID, X-Request-ID}
```

**Step 3 — Send the message to `/run`:**
```python
POST {agent_url}/run
body: {
  "appName": "{app_name}",
  "userId": "orchestrator",
  "sessionId": "{session_id}",
  "newMessage": {
    "role": "user",
    "parts": [{"text": json.dumps(payload)}]
  }
}
```
The `payload` is extracted from `task_data["message"]["parts"][0]["data"]` — the actual input dict (e.g., `ProvisioningInput` serialised to dict).

**Step 4 — Parse the response:**
The `/run` endpoint returns a JSON array of `Event` objects. The function iterates in reverse (last event first) looking for an event with a `"text"` part. The first valid JSON string found is returned:
```python
for event in reversed(events):
    for part in event["content"]["parts"]:
        if "text" in part:
            return json.loads(part["text"])
return {}  # fallback if no text part found
```

#### `_A2AClient` Wrapper

```python
class _A2AClient:
    def __init__(self, url: str): self._url = url

    async def submit(self, **kwargs) → dict:
        # Serialises dataclass kwargs to dict (dataclasses.asdict)
        # Wraps in ADK task envelope
        # Calls _call_sub_agent()
```

Used by the orchestrator's `route()` function:
```python
await provisioning_agent.submit(
    resource_type=normalized.resource_type,
    resource_name=normalized.resource_name,
    ...
    correlation_id=input.correlation_id,
)
```

#### Agent Input Extraction (`_run_async_impl`)

Each sub-agent's `_run_async_impl(ctx: InvocationContext)` extracts the payload:
```python
user_text = ctx.user_content.parts[0].text   # JSON string
task_data = json.loads(user_text)
inp = ProvisioningInput(**task_data)          # Pydantic model validation
```

#### Agent Output Emission

After processing, agents yield exactly one `Event`:
```python
yield Event(
    invocation_id=ctx.invocation_id,
    author=self.name,
    content=genai_types.Content(
        role="model",
        parts=[genai_types.Part(text=output.model_dump_json())]
    ),
)
```

The `model_dump_json()` output is what `_call_sub_agent` parses as the return value.

---

### 4.3b Correlation Context — Request Tracing

**File**: `contracts/shared/correlation.py`

Every request through the system carries two IDs:
- **`correlation_id`** — stable across all hops (web → orchestrator → provisioning → DAG → notification). Identifies a logical user request end-to-end.
- **`request_id`** — fresh per A2A hop. Identifies a single agent invocation.

#### `CorrelationContext` dataclass

```python
@dataclass
class CorrelationContext:
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    request_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def new_request(self) → CorrelationContext:
        # Same correlation_id, fresh request_id (use when forwarding)

    @classmethod
    def from_ids(cls, correlation_id, request_id) → CorrelationContext:
        # Propagate existing IDs (used in _run_async_impl to restore context)
```

#### Context storage

Stored in a Python `ContextVar` — async-task-local (safe under asyncio, no thread safety issues):
```python
_context_var: ContextVar[CorrelationContext] = ContextVar("correlation_context", ...)
```

Functions:
- `get_correlation_context()` — read current context
- `set_correlation_context(ctx)` — overwrite (used in `_run_async_impl`)
- `new_correlation_context()` — create + store fresh context

#### Lifecycle

```
1. HTTP request arrives at web-backend
   → extract_correlation_headers(request.headers)
     → reads X-Correlation-ID (reuses if present, else uuid4())
     → reads X-Request-ID
     → stores in ContextVar

2. web-backend calls orchestrator via HTTP POST
   → inject_correlation_headers(headers)
     → reads from ContextVar
     → adds X-Correlation-ID + X-Request-ID to outgoing headers

3. Orchestrator _run_async_impl receives correlation_id in OrchestratorInput
   → set_correlation_context(CorrelationContext(correlation_id, request_id))

4. Orchestrator calls sub-agent via _call_sub_agent
   → inject_correlation_headers(headers) → same correlation_id forwarded

5. Sub-agent receives correlation_id in ProvisioningInput/EnquiryInput/FAQInput
   → passes inp.correlation_id to all MCP calls, DB records, audit events

6. Every DB row (infra_requests, provisioning_jobs, audit_events) stores correlation_id
   → Full request trace reconstructable from any single ID
```

---

### 4.4 Contracts (Schemas)

All inter-component interfaces are defined as **Pydantic v2 models** in `contracts/`. This ensures runtime validation at every boundary.

#### Agent I/O Contracts

| File | Key Models |
|------|-----------|
| `contracts/agents/orchestrator.py` | `OrchestratorInput`, `OrchestratorOutput`, `Outcome` enum |
| `contracts/agents/provisioning.py` | `ProvisioningInput`, `ProvisioningConfirmationOutput`, `ProvisioningQueuedOutput`, `VMParameters`, `BucketParameters`, `VPCParameters` |
| `contracts/agents/enquiry.py` | `EnquiryInput`, `EnquiryFoundOutput`, `EnquiryListOutput`, `EnquiryNotFoundOutput`, `ResourceSummary` |
| `contracts/agents/faq.py` | `FAQInput`, `FAQAnsweredOutput`, `FAQNoResultsOutput`, `Source` |

#### Event Schemas (PubSub)

PubSub events are versioned with `schema_version="1.0.0"` and are **additive-only** (breaking changes blocked by CI schema validation gate).

| Model | Topic | Description |
|-------|-------|-------------|
| `ProvisioningRequestEvent` | infraops.provisioning.requests | Published by provisioning-agent after user confirms |
| `ProvisioningStatusEvent` | infraops.provisioning.status | Published by Airflow on status transitions |
| `AuditEventMessage` | infraops.audit.events | Published by agents and DAG tasks |

#### Database Schemas

| File | Key Models |
|------|-----------|
| `contracts/schemas/provisioning_job.py` | `ProvisioningJob`, `ProvisioningJobCreate`, `JobStatus` enum |
| `contracts/schemas/infra_request.py` | `InfraRequest`, `InfraRequestCreate`, `RequestStatus`, `ChannelType`, `IntentType` |
| `contracts/schemas/audit_event.py` | `AuditEvent`, `AuditEventCreate`, `AuditEventType` enum (21 types) |
| `contracts/schemas/user_role.py` | `UserRoleType`, `DeveloperGuardrails` |
| `contracts/schemas/faq_query.py` | `FAQQuery`, `FAQQueryCreate`, `RetrievedChunk` |

#### Shared Utilities

| File | Description |
|------|-------------|
| `contracts/shared/logging.py` | `configure_logging()`, `get_logger()`, structured JSON with redaction |
| `contracts/shared/correlation.py` | `CorrelationContext`, `new_correlation_context()`, header injection |
| `contracts/shared/audit.py` | `emit_audit_event()` — swallows exceptions so audit never blocks flow |
| `contracts/shared/circuit_breaker.py` | `CircuitOpenError` exception |
| `contracts/shared/metrics.py` | `start_metrics_server()` for Prometheus |

---

### 4.5 Workflows (Airflow DAGs)

Airflow DAGs are **thin orchestration wrappers** (ADR-0001). Business logic lives in business_logic, not DAGs. DAGs handle sequencing, retries, and rollback.

#### provision_vm_dag

**File**: `workflows/dags/provision_vm_dag.py`  
**Schedule**: `None` (triggered programmatically by provisioning-agent)  
**Trigger**: PubSub message + explicit DAG trigger via Airflow REST API

**Task dependency graph**:

```
wait_for_message ──→ update_in_progress ──→ dry_run_validate ──→ provision_vm
                                                                       │
                                                              ┌────────┴────────┐
                                                              ▼                 ▼ (on failure)
                                                      register_backstage    rollback_vm
                                                              │              (TriggerRule.ONE_FAILED)
                                                              ▼                 ▼
                                                      update_succeeded      update_failed
                                                                         (TriggerRule.ALL_SUCCESS)
```

**Retry policy for provision_vm**: 3 retries, exponential backoff `max(30, 2^retry * 30 ± jitter)` seconds, max 300s delay.

**Key task details**:

| Task | Type | Description |
|------|------|-------------|
| `wait_for_message` | PubSubPullSensor | Polls subscription, ACKs messages, decodes ProvisioningRequestEvent |
| `update_in_progress` | PythonOperator | SET status='in_progress', push job_data to XCom |
| `dry_run_validate` | PythonOperator | create_vm(dry_run=True) — validate params only |
| `provision_vm` | PythonOperator | create_vm(dry_run=False) — real GCP call, retry on failure |
| `register_backstage` | PythonOperator | Register entity in Backstage catalog |
| `update_succeeded` | PythonOperator | SET status='succeeded', gcp_resource_id=... |
| `rollback_vm` | PythonOperator | Delete each entry in rollback_resources |
| `update_failed` | PythonOperator | SET status='failed', error_message=... |

**Database writes**: All via raw `psycopg2` (synchronous; asyncpg not compatible with Airflow task runners). PostgreSQL trigger fires `pg_notify` on every `UPDATE OF status`.

---

### 4.6 Web Backend

**Framework**: FastAPI  
**Port**: 8000  
**Auth**: JWT Bearer + X-API-Key via middleware  
**Database**: asyncpg connection pool (min=2, max=10)

#### Application Startup (`web/backend/main.py`)

```python
@asynccontextmanager
async def lifespan(app):
    await init_db_pool()      # asyncpg pool for SSE listener
    yield
    await close_db_pool()     # cleanup on shutdown
```

CORS origins configurable via `CORS_ORIGINS` env (default `http://localhost:3000`).

#### Router Summary

| Path prefix | File | Description |
|------------|------|-------------|
| `/api/v1/auth` | `routers/auth.py` | Login, /me, rotate-key |
| `/api/v1/requests` | `routers/requests.py` | Submit NL request, clarify |
| `/api/v1/jobs` | `routers/jobs.py` | Confirm, cancel, get, list |
| `/api/v1/jobs/{id}/stream` | `routers/sse.py` | SSE real-time status |

#### Authentication Middleware (`web/backend/middleware/auth.py`)

Checks every request except `/health`, `/`, `/api/v1/auth/login`.

```
Request
  │
  ├─ "Authorization: Bearer <jwt>"
  │    → Decode JWT (HS256, JWT_SECRET)
  │    → Set request.state.user_id = jwt.sub
  │    → Set request.state.user_role = { role, api_key_expires_at }
  │
  └─ "X-API-Key: <key>"
       → mcp-postgres.verify_api_key(api_key)
       → bcrypt.checkpw(provided_key, stored_hash)
       → Set request.state.user_id, request.state.user_role

Brute-force protection: 5 failures per IP per 60s → 429
```

#### SSE Endpoint (`routers/sse.py`)

**Critical design**: Avoids race condition by emitting current status immediately.

```python
async def job_status_stream(job_id, db_listener, dsn):
    # 1. Fetch current status immediately (handles already-completed jobs)
    current = await _fetch_current_status(str(job_id), dsn)
    if current:
        yield { "event": "status", "data": {"job_id": ..., "status": current} }
        if current in TERMINAL_STATUSES:
            yield { "event": "done", "data": "" }
            return

    # 2. Listen for future NOTIFY events via asyncpg
    async for payload in db_listener.listen("infraops_job_status"):
        data = json.loads(payload)
        if data["job_id"] != str(job_id):
            continue       # filter to this job only
        yield { "event": "status", ... }
        if data["status"] in TERMINAL_STATUSES:
            yield { "event": "done", "data": "" }
            return
```

Terminal statuses that close the stream: `completed`, `succeeded`, `failed`, `rolled_back`, `cancelled`.

---

### 4.7 Web Frontend

**Framework**: React 18 + TypeScript  
**State Management**: Zustand  
**Styling**: TailwindCSS  
**Build**: Vite  
**Port**: 3001 (Docker), 5173 (dev server)

#### Application Shell

```
App.tsx
  ├─ useAuth() → checks JWT in localStorage
  ├─ Not authenticated → LoginPage
  └─ Authenticated → AppShell
       ├─ Header (user info, theme toggle, logout)
       ├─ Sidebar (conversation list)
       └─ ChatWindow (main content)
            ├─ MessageList (conversation messages)
            └─ InputComposer (text input + submit)
```

#### Conversation Store (`src/store/conversations.ts`)

Zustand store. Max 5 conversations retained (oldest trimmed).

```typescript
interface Conversation {
  id: string
  title: string
  created_at: Date
  messages: Message[]
  trace: AgentTraceEntry[]
  active_job_id: string | null
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  intent: 'provision' | 'enquiry' | 'faq' | null
  loading: boolean
  confirmation: IntentConfirmation | null    // shown as IntentConfirmationCard
  clarification: ClarificationPayload | null  // shown as ClarificationCard
  error: ErrorPayload | null
  job_statuses: JobStatusUpdate[]            // timeline entries
  faq_sources: Source[] | null
  enquiry_data: EnquiryData | null
}
```

#### Key Hooks

| Hook | Description |
|------|-------------|
| `useSubmitRequest` | Submit NL request, handle 5 response types, update store |
| `useJobStream` | Open SSE stream when job_id set, append status updates to message |
| `useAuth` | JWT validation, login/logout, token refresh |
| `useJobConfirm` | POST /jobs/{id}/confirm, set active job, start SSE stream |
| `useJobCancel` | POST /jobs/{id}/cancel |
| `useCountdown` | 20-minute deadline countdown timer for confirmation card |

#### Message Rendering

Each message renders differently based on `intent` and `loading` state:

| State | Component | Description |
|-------|-----------|-------------|
| `loading=true` | LoadingBubble | Animated spinner |
| `intent=provision, confirmed=false` | IntentConfirmationCard | Summary + Confirm/Rephrase buttons + countdown |
| `intent=provision, confirmed=true` | JobStatusTimeline | Live status progress bar |
| `intent=enquiry` | EnquiryResultCard | Resource metadata table |
| `intent=faq` | FAQAnswerCard | Markdown answer + source links |
| `intent=clarification` | ClarificationCard | Question + free-text input |
| `error!=null` | ErrorBubble | Error message with code |

---

### 4.8 Infrastructure & Database

#### Database Schema

PostgreSQL 15. All tables use UUID primary keys. `updated_at` maintained automatically by `set_updated_at` trigger.

**user_roles**
```sql
user_id            TEXT PRIMARY KEY           -- e.g. "cg4ai@gmail.com"
role               user_role_type             -- developer | platform_engineer
api_key_hash       TEXT                       -- bcrypt hash
api_key_expires_at TIMESTAMPTZ                -- 90-day expiry (rotatable)
daily_provisioning_count  INTEGER DEFAULT 0
daily_count_reset_at      TIMESTAMPTZ         -- reset daily
```

**infra_requests**
```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
correlation_id  UUID NOT NULL
raw_input       TEXT NOT NULL
channel         channel_type                  -- web | email
intent          intent_type                   -- provision | enquiry | faq
confidence      FLOAT
normalized_params JSONB
requesting_user TEXT NOT NULL                 -- FK to user_roles.user_id
user_role       user_role_type NOT NULL
status          request_status DEFAULT 'received'
confirmation_summary TEXT
expires_at      TIMESTAMPTZ DEFAULT (created_at + INTERVAL '20 minutes')
email_thread_id TEXT                          -- required if channel=email
email_message_id TEXT
```

**provisioning_jobs**
```sql
id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
infra_request_id UUID REFERENCES infra_requests(id)
correlation_id   UUID NOT NULL
idempotency_key  TEXT UNIQUE NOT NULL        -- SHA256(type:name:region)
resource_type    resource_type_enum          -- compute_instance | storage_bucket | vpc_network
resource_name    TEXT NOT NULL
region           TEXT NOT NULL
zone             TEXT
parameters       JSONB                       -- VMParameters | BucketParameters | VPCParameters
status           job_status DEFAULT 'awaiting_confirmation'
retry_count      INTEGER DEFAULT 0 CHECK (retry_count <= 3)
gcp_resource_id  TEXT                       -- set after successful provisioning
rollback_resources JSONB DEFAULT '[]'::jsonb
error_message    TEXT
requesting_user  TEXT REFERENCES user_roles(user_id)
dry_run          BOOLEAN DEFAULT FALSE
created_at       TIMESTAMPTZ DEFAULT NOW()
updated_at       TIMESTAMPTZ DEFAULT NOW()
completed_at     TIMESTAMPTZ
```

**LISTEN/NOTIFY Trigger**:
```sql
CREATE TRIGGER job_status_notify
  AFTER UPDATE OF status ON provisioning_jobs
  FOR EACH ROW
  EXECUTE FUNCTION notify_job_status_change();
-- Fires pg_notify('infraops_job_status', json_build_object(
--   'job_id', NEW.id::text, 'status', NEW.status::text, ...
-- ))
```

**audit_events**
```sql
id          UUID PRIMARY KEY
event_type  TEXT NOT NULL              -- one of 21 AuditEventType values
actor       TEXT NOT NULL              -- user_id or service name
agent_name  TEXT NOT NULL
payload     JSONB                      -- auto-redacted (api_key, password, token removed)
correlation_id  UUID
request_id      UUID
timestamp   TIMESTAMPTZ DEFAULT NOW()
```

#### Migrations

Located in `infrastructure/db/migrations/`. Applied in filename order by `init_system.py`. Each is tracked in `schema_migrations` table (idempotent).

| Migration | Description |
|-----------|-------------|
| 001_initial_schema.sql | Tables, enums, indexes, set_updated_at trigger |
| 002_notify_trigger.sql | pg_notify trigger for SSE |
| 003_immutable_audit.sql | Audit events made append-only (no update/delete) |
| 004_add_user_role_to_provisioning_jobs.sql | Add user_role column |
| 005_add_expires_at_to_provisioning_jobs.sql | Add expires_at column |
| 006_add_clarification_to_infra_requests.sql | Add clarification_question, clarification_rounds |
| 007_add_password_hash.sql | Add password_hash column to user_roles |

#### Initialization (`infrastructure/scripts/init_system.py`)

Runs at stack startup via `infraops-init` Docker service. Steps:
1. Wait for PostgreSQL readiness (30 retries, 2s delay)
2. Run all pending migrations in order
3. Wait for PubSub emulator readiness
4. Create PubSub topics and subscriptions
5. Create default developer user (`cg4ai@gmail.com` / `password`)
6. Create default platform engineer (`platformengg@infraops.com` / `password`)

---

### 4.9 Observability

#### Metrics

All agents expose a Prometheus metrics server:

| Service | Metrics Port |
|---------|-------------|
| orchestrator-agent | 9001 |
| provisioning-agent | 9002 |
| enquiry-agent | 9003 |
| faq-agent | 9004 |

Key metrics collected:
- `infraops_request_duration_seconds{agent, intent, outcome}` — request latency histogram
- `infraops_job_status_total{status}` — job status counter
- `infraops_guardrail_violations_total{violation_type}` — guardrail events
- `infraops_circuit_breaker_state{service}` — circuit breaker open/closed
- `infraops_pubsub_publish_duration_seconds{topic}` — PubSub publish latency
- `infraops_llm_tokens_total{model, type}` — LLM token usage
- `infraops_gcp_api_duration_seconds{operation, resource_type}` — GCP API latency

#### Structured Logging

All services use `structlog` with JSON output:
```json
{
  "event": "job_in_progress",
  "job_id": "fdd2f690-...",
  "correlation_id": "1e8badd7-...",
  "request_id": "a1b2c3d4-...",
  "agent_name": "provisioning_agent",
  "timestamp": "2026-05-17T02:49:12.000Z",
  "level": "info"
}
```

Sensitive fields automatically redacted: `api_key`, `api_key_hash`, `password`, `token`, `secret`, `authorization`.

#### Audit Trail

21 event types recorded to `audit_events` table with full payload (redacted):

```
request_received → intent_classified → [clarification_requested →] confirmation_sent
  → request_confirmed → job_created → job_started → [job_retried →]
  → job_succeeded | (rollback_started → rollback_completed → job_failed)
```

---

## 5. State Machines

### InfraRequest Status

```
               ┌─────────────────────────────────────────────────────────────┐
               │                                                             │
    received ──→ classifying ──→ clarifying (max 2 rounds) ──┐              │
               │                                              │              │
               └────────→ awaiting_confirmation ←────────────┘              │
                                  │                                          │
                           user confirms                                     │
                                  │                                          │
                           confirmed ──────────────────────────→ fulfilled   │
                                                                             │
    rejected ←──────── (confidence < 0.55, email channel) ─────────────────-┤
    expired  ←──────── (20 min timeout on awaiting_confirmation) ───────────┘
    failed   ←──────── (downstream provisioning failed)
```

### ProvisioningJob Status

```
                                         ┌──────────────────────────────────┐
                                         │                                  │
    awaiting_confirmation ──→ queued ──→ in_progress ──→ [retrying] ──→ succeeded
           │                    │                              │
      (user cancel)        (user cancel)                  rollback ──→ failed
           │                    │
           └────→ cancelled ←───┘

    Job auto-expires from awaiting_confirmation after 20 minutes.
    Retry limit: 3 retries before declaring failed.
```

---

## 6. Security Model

### Authentication

Two authentication methods, both checked by `AuthMiddleware`:

**JWT Bearer Token (login flow)**:
- Obtained via `POST /api/v1/auth/login` with email + password
- Algorithm: HS256, signing key: `JWT_SECRET` env var
- Payload: `{ sub: user_id, role: user_role, iat, exp }`
- Expiry: 8 hours
- Use case: Browser sessions

**X-API-Key (service/legacy)**:
- bcrypt hash stored in `user_roles.api_key_hash`
- Expiry: 90 days (rotatable via `POST /api/v1/auth/rotate-key`)
- Use case: Service-to-service calls, programmatic access

### Authorization

| User Role | Can provision | Regions | Machine types | VPC | Daily limit |
|-----------|--------------|---------|---------------|-----|-------------|
| `developer` | Yes | us-central1, us-east1, europe-west1 | e2-standard-2/4/8 | No | 10/day |
| `platform_engineer` | Yes | Any | Any | Yes | Unlimited |

### Security Controls

| Control | Implementation |
|---------|---------------|
| Brute-force protection | 5 failed auth attempts per IP per 60s → 429 |
| Password hashing | bcrypt with 12 rounds |
| API key hashing | bcrypt (keys never stored in plaintext) |
| JWT expiry | 8-hour tokens, session invalidated on logout |
| Audit trail | All actions recorded with actor, timestamp, correlation_id |
| Sensitive field redaction | api_key, password, token auto-redacted in logs and audit events |
| CORS | Configurable `CORS_ORIGINS` env var |
| Confirmation timeout | 20-minute window for provisioning confirmations |

---

## 7. Configuration Reference

All configuration via environment variables. Copy `.env.example` to `.env` before starting the stack.

### Required Secrets

| Variable | Description |
|----------|-------------|
| `GCP_SA_KEY_PATH` | Path to GCP service account JSON (for Compute, Storage, VPC APIs) |
| `GMAIL_CREDENTIALS_PATH` | Path to Gmail OAuth2 JSON |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | LLM provider API keys (via LiteLLM) |
| `LITELLM_MASTER_KEY` | LiteLLM gateway authentication key |
| `JWT_SECRET` | JWT signing secret (use a strong random value in production) |
| `AIRFLOW_FERNET_KEY` | Airflow connection encryption key |

### Application Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | — | Google Cloud project ID |
| `DATABASE_URL` | `postgresql://infraops:admin@postgres:5432/infraops` | PostgreSQL connection |
| `PUBSUB_EMULATOR_HOST` | — | PubSub emulator (local only; unset in production) |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant vector DB |
| `LITELLM_GATEWAY_URL` | `http://litellm:4000` | LiteLLM gateway |
| `INTENT_CLASSIFICATION_MODEL` | — | Model for intent classification |
| `FAQ_GENERATION_MODEL` | `gpt-4o-mini` | Model for FAQ answer generation |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for knowledge base |
| `BACKSTAGE_API_URL` | `http://backstage:7007/api` | Backstage catalog API |
| `BACKSTAGE_API_TOKEN` | `changeme-backstage-token` | Backstage auth token |
| `BACKSTAGE_REQUIRED` | `false` | Whether Backstage failure triggers rollback |

### Guardrail Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_REGIONS` | `us-central1,us-east1,europe-west1` | Regions developers may use |
| `ALLOWED_MACHINE_TYPES` | `e2-standard-2,e2-standard-4,e2-standard-8` | Machine types for developers |
| `ALLOWED_STORAGE_CLASSES` | `STANDARD,NEARLINE` | Storage classes for developers |
| `DEVELOPER_DAILY_LIMIT` | `10` | Max provisioning ops per developer per day |

### Default Users (set by `infraops-init`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_USER_ID` | `cg4ai@gmail.com` | Developer user email |
| `DEFAULT_USER_ROLE` | `developer` | Developer user role |
| `DEFAULT_PASSWORD` | `password` | Developer user password |
| `PLATFORM_USER_ID` | `platformengg@infraops.com` | Platform engineer email |
| `PLATFORM_USER_ROLE` | `platform_engineer` | Platform engineer role |
| `PLATFORM_PASSWORD` | `password` | Platform engineer password |

---

## 8. Service Ports

### Application Services

| Service | Port | Protocol |
|---------|------|----------|
| web-frontend | 3001 | HTTP (Nginx) |
| web-backend | 8000 | HTTP (FastAPI) |
| orchestrator-agent | 8001 | HTTP (ADK A2A) |
| provisioning-agent | 8002 | HTTP (ADK A2A) |
| enquiry-agent | 8003 | HTTP (ADK A2A) |
| faq-agent | 8004 | HTTP (ADK A2A) |
| airflow-webserver | 8080 | HTTP |

### Infrastructure Services

| Service | Port | Protocol |
|---------|------|----------|
| postgres | 5432 | PostgreSQL wire protocol |
| redis | 6379 | Redis protocol |
| pubsub-emulator | 8085 | HTTP (gRPC) |
| litellm | 4000 | HTTP (OpenAI-compatible) |
| qdrant | 6333 | HTTP |
| qdrant (gRPC) | 6334 | gRPC |
| prometheus | 9090 | HTTP |
| grafana | 3000 | HTTP |
| backstage | 7007 | HTTP |

### MCP Servers (SSE transport)

| Service | Port |
|---------|------|
| mcp-gcp-resource | 8090 |
| mcp-pubsub | 8091 |
| mcp-airflow | 8094 |
| mcp-knowledge-base | 8093 |
| mcp-backstage | 8096 |
| mcp-gmail | 8095 |

### Metrics Endpoints (Prometheus scrape)

| Service | Port |
|---------|------|
| orchestrator-agent metrics | 9001 |
| provisioning-agent metrics | 9002 |
| enquiry-agent metrics | 9003 |
| faq-agent metrics | 9004 |

---

## 9. Architectural Decisions (ADRs)

### ADR-0001: Skills as Business Logic Layer

**Decision**: All business logic lives in `business_logic/`. Agents and DAGs are thin orchestration layers.

**Call chain**: `Agent → Skill → MCP Server → External System`

**Why**: Skills are reusable across agents (e.g., `create_vm` skill used by both provisioning-agent and Airflow DAG), testable without agent or DAG overhead, and prevent logic duplication.

---

### ADR-0002: Single Resource Per Request

**Decision**: Each `InfraRequest` maps to exactly one resource operation. Compound requests ("provision two VMs") are rejected at classification time with a clarification request.

**Why**: Simplifies the state machine, makes idempotency keys unambiguous, and provides a clear one-to-one confirmation UX.

---

### ADR-0003: Airflow DAG Owns Job State

**Decision**: Only the Airflow DAG writes terminal job state (`succeeded`, `failed`) to PostgreSQL. The notification service subscribes to PubSub but does not write state.

**Why**: Eliminates dual-write race conditions where both the agent and notification service could update state simultaneously.

---

### ADR-0004: Two-Phase Provisioning State

**Decision**: "Pending" split into `awaiting_confirmation` (user hasn't confirmed) and `queued` (confirmed, waiting for Airflow). 

**State machine**: `awaiting_confirmation → queued → in_progress → retrying → succeeded | rollback → failed`

**Why**: Clear semantics — only `awaiting_confirmation` times out; `queued` persists until Airflow picks it up. Cancellation is meaningful at each state.

---

### ADR-0005: Backstage Registration is a Hard Requirement

**Decision**: Every provisioned resource must be registered in Backstage. If Backstage registration fails after GCP provisioning succeeds, the DAG triggers rollback and marks the job failed.

**Trade-off**: A Backstage outage will cause provisioning to fail and rollback even though the GCP resource was created. Mitigation: `BACKSTAGE_REQUIRED=false` env flag for local development.

**Why**: Keeps the Backstage catalog consistent with actual GCP state.

---

### ADR-0006: Rollback Resources Appended After Create

**Decision**: `rollback_resources` starts as an empty list. Each resource is appended immediately after a successful GCP `create` call, not pre-populated from dry-run planning.

**Why**: Rollback deletes exactly what was actually created. No spurious 404 errors from trying to delete resources that were never created. Provides accurate audit trail.

---

## 10. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Agent Framework | Google Agent Development Kit (ADK) | latest | Multi-agent orchestration, A2A protocol |
| Workflow Engine | Apache Airflow | 2.9 with CeleryExecutor | DAG-based job orchestration |
| LLM Gateway | LiteLLM | latest | Unified LLM access (all LLM calls must go through LiteLLM — direct provider SDK is prohibited) |
| Web Backend | FastAPI + asyncpg | latest | REST API, SSE, auth, DB pool |
| Web Frontend | React + TypeScript + Zustand + TailwindCSS + Vite | 18/5 | Chat UI with real-time updates |
| Database | PostgreSQL | 15 | All persistent state |
| Vector DB | Qdrant | latest | Hybrid BM25 + vector FAQ search |
| Message Queue | Google Cloud PubSub (emulator locally) | — | Event-driven job handoff to Airflow |
| Developer Catalog | Backstage | latest | Resource catalog and metadata |
| Email | Gmail API (OAuth2) | — | Email-based request input and notifications |
| Monitoring | Prometheus + Grafana | latest | Metrics collection and dashboards |
| Schema Validation | Pydantic v2 | 2.x | Runtime validation at all boundaries |
| HTTP Client | httpx | latest | Async HTTP (agents, skills, backend) |
| Async Runtime | asyncio / asyncpg | — | Async/await throughout Python services |
| Auth - Hashing | bcrypt | — | API key and password storage |
| Auth - Tokens | PyJWT (HS256) | — | Session tokens |
| Logging | structlog | latest | Structured JSON logging with redaction |
| Testing | pytest + pytest-asyncio | — | Unit, integration, contract, workflow tests |
| Linting | Ruff | — | Code quality |
| Formatting | Black | — | Code style |
| Type Checking | mypy | — | Static type analysis |
| Containers | Docker + Docker Compose | — | Local orchestration |
| Task Broker | Redis | 7 | Airflow Celery broker |

---

## 11. Local Development

### Prerequisites

- Docker Desktop with Docker Compose
- Python 3.11+
- Node.js 18+ (for frontend)
- GCP service account JSON with Compute, Storage, VPC Admin permissions
- Gmail OAuth2 credentials JSON

### Starting the Full Stack

```bash
# 1. Copy and populate environment variables
cp .env.example .env
# Edit .env: set GCP_SA_KEY_PATH, API keys, etc.

# 2. Start all services
docker compose -f docker/docker-compose.yml --env-file .env up -d

# 3. View init logs (migrations + PubSub setup + users created)
docker compose -f docker/docker-compose.yml --env-file .env logs infraops-init

# 4. Check all services are healthy
docker compose -f docker/docker-compose.yml --env-file .env ps
```

### Default Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Web UI | http://localhost:3001 | cg4ai@gmail.com / password |
| Airflow | http://localhost:8080 | admin / (set in .env) |
| Backstage | http://localhost:7007 | Guest (click "Enter as Guest") |
| Grafana | http://localhost:3000 | admin / (set in .env) |
| Prometheus | http://localhost:9090 | — |
| LiteLLM | http://localhost:4000 | — |

### Rebuilding a Single Service

```bash
docker compose -f docker/docker-compose.yml --env-file .env \
  up -d --no-deps --build <service-name>
# e.g. --build orchestrator-agent
```

### Seeding the Knowledge Base

```bash
python infrastructure/scripts/seed_knowledge_base.py \
  --knowledge-dir docs/knowledge/
```

### Running Tests

```bash
# Unit tests (no external services)
pytest tests/unit -m "not integration" --tb=short

# Contract tests (schema validation only)
pytest tests/contract -m "contract" --tb=short

# Integration tests (requires full Docker Compose stack)
pytest tests/integration -v --env local

# Workflow tests (Airflow DAG unit tests)
pytest tests/workflow -v
```

### Stopping the Stack

```bash
docker compose -f docker/docker-compose.yml --env-file .env stop

# Full reset (drops all data)
docker compose -f docker/docker-compose.yml --env-file .env down -v
```

---

## 12. Key Design Patterns

### Pattern 1: Protocol-Based Dependency Injection

All agents and skills accept dependencies via `Protocol` interfaces, making them testable without external services:

```python
class PostgresClient(Protocol):
    async def update_job_status(self, job_id: str, status: str) -> dict: ...

class GcpClient(Protocol):
    async def create_vm(self, project_id: str, zone: str, ...) -> dict: ...

async def create_vm(
    ...
    gcp_client: GcpClient,       # inject mock in tests
    postgres_client: PostgresClient,
) -> ProvisionResult:
    ...
```

### Pattern 2: Correlation Context Propagation

Every request carries `correlation_id` and `request_id` through all service boundaries. These are:
- Set by web-backend on request arrival
- Passed in A2A call payloads (JSON body)
- Passed in PubSub event payloads
- Bound to structlog context vars for log correlation
- Stored in audit_events and provisioning_jobs tables

```python
# In each agent:
bind_request_context(
    correlation_id=str(inp.correlation_id),
    request_id=str(inp.request_id),
    agent_name="provisioning_agent"
)
```

### Pattern 3: Idempotency via SHA256 Keys

Provisioning requests use a deterministic idempotency key to prevent duplicate resource creation:

```python
idempotency_key = hashlib.sha256(
    f"{resource_type}:{resource_name}:{region}".encode()
).hexdigest()
```

On resubmission with the same `resource_type:resource_name:region`, the system returns the existing job rather than creating a new one.

### Pattern 4: Two-Phase Confirmation

All destructive operations require explicit user confirmation:

1. **Phase 1** (confirmed=False): Create job in `awaiting_confirmation`, return human-readable summary with 20-min expiry
2. **Phase 2** (confirmed=True): User explicitly confirms → move to `queued` → publish to PubSub → trigger Airflow

This pattern prevents accidental resource creation and provides a natural audit point.

### Pattern 5: Append-Only Rollback Resources

Rollback list is populated **only after** each successful GCP create (ADR-0006):

```python
# In provision_vm skill — AFTER GCP create succeeds:
await postgres_client.update_job_status(
    job_id=str(job_id),
    status="in_progress",
    rollback_resources=[{
        "resource_type": "compute_instance",
        "resource_id": gcp_resource_id,
        "zone": zone,
    }]
)
```

### Pattern 6: Event-Driven Status Updates (NOTIFY/LISTEN)

No polling. Status changes propagate via:
1. Airflow DAG: `psycopg2 UPDATE provisioning_jobs SET status=...`
2. PostgreSQL trigger: `pg_notify('infraops_job_status', json_payload)`
3. Web backend: `asyncpg LISTEN infraops_job_status` in SSE endpoint
4. Browser: `EventSource` consumer updates JobStatusTimeline in real-time

### Pattern 7: Thin DAGs, Thin Agents

Neither agents nor DAGs contain provisioning logic (ADR-0001):

```
❌ BAD:  provisioning_agent calls GCP API directly
❌ BAD:  Airflow task contains VM creation logic
✅ GOOD: provisioning_agent calls business_logic.gcp_compute.create_vm()
✅ GOOD: Airflow task calls business_logic.gcp_compute.create_vm()
```

This means `create_vm` skill is tested once and reused in both the agent (for dry-run validation) and the DAG (for actual execution).

---

*End of Documentation — Agentic InfraOps Platform v1.0*
