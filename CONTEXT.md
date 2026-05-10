# Domain Context: Agentic InfraOps Platform

**Version**: 0.1.0 | **Last updated**: 2026-05-10

This file defines the canonical domain language for the InfraOps platform. All code, contracts, documentation, and conversations MUST use these terms consistently.

---

## Skill

A **Skill** is a reusable Python package that encapsulates business logic for a specific operational capability. Skills sit between Agents and MCP Servers in the call chain:

```
Agent → Skill → MCP Server → External System
```

A Skill is responsible for:
- Parameter validation and normalisation
- Idempotency enforcement
- Dry-run logic (validate without side effects)
- Rollback procedures
- Retry awareness (signals retry eligibility to callers)

A Skill is NOT responsible for:
- Direct external system calls (those belong in MCP Servers)
- Routing or intent classification (those belong in Agents)
- Workflow orchestration (that belongs in Airflow DAGs)

**Synonym to avoid**: "tool" (overloaded with MCP tool meaning), "capability", "module"

---

## Channel

A **Channel** is the input interface through which a user submits a request to the platform. Phase 1 supports two channels:

- **`web`** — the custom web UI (text-based request interface in a browser)
- **`email`** — inbound email parsed via Gmail API

The enum value `web` (not `chatbot`, not `web_ui`) is canonical across all code, schemas, database rows, PubSub events, and audit logs.

Future channels (`slack`, `api`, `teams`) extend this enum without ambiguity.

---

## InfraRequest

An **InfraRequest** represents exactly one user request for exactly one operation on exactly one resource. It is always 1:1 with at most one ProvisioningJob.

Compound requests (e.g. "create a VM and a bucket") are rejected at normalisation time with a message asking the user to submit them as separate requests.

**Synonym to avoid**: "user request" (too generic), "task" (overloaded with ADK task meaning)

---

## Guardrail Violation

A **Guardrail Violation** is a role-based policy rejection. The request is structurally valid GCP — a platform engineer submitting the same request would succeed. It is rejected solely because of *who is asking*, not *what they asked for*.

- Enforced by: **Orchestrator Agent** (before the request reaches any Skill)
- Audit event: `guardrail_violation`
- Error code: `GUARDRAIL_VIOLATION`
- User message: explains which parameter exceeded their role's allowed values and that a platform engineer can run the same request

**Example**: Developer requests `machine_type: n2-standard-96` — valid GCP, but outside the developer allowed list (`e2-standard-2/4/8`).

---

## Validation Error

A **Validation Error** is a schema or format failure that would fail for any user regardless of role. The input does not conform to what the platform accepts at all.

- Enforced by: **Skills** (parameter schema validation) and **Web backend** (request body schema)
- Audit event: `request_rejected`
- Error code: `VALIDATION_ERROR`
- User message: specifies which field is invalid and what is expected

**Example**: `region: invalid-region-xyz`, `machine_type: ""`, missing required field.

**Synonym to avoid**: Do not use "validation error" to mean a guardrail violation. They are different failures, logged differently, and produce different user-facing messages.

---

## correlation_id vs request_id

Two trace identifiers appear on every A2A task, PubSub message, audit event, and log entry:

**`correlation_id`** — UUID generated once when the InfraRequest is first created. Propagated unchanged through every downstream operation: A2A calls, PubSub messages, Airflow task logs, SSE events, audit events, email notifications. This is the distributed trace ID for one user interaction end-to-end. Never changes. Never re-used.

**`request_id`** — The `InfraRequest.id` UUID. A business domain identifier that lets any service or log consumer look up the originating InfraRequest directly. Stable for the lifetime of a request. Distinct from `correlation_id` in that it references a specific database row, not just a trace grouping.

**Usage rule**: Both MUST appear on every log entry, PubSub message, A2A task input/output, and audit event. OpenTelemetry span context (W3C `traceparent` header) carries distributed tracing span correlation separately — `request_id` and `correlation_id` are business-level fields, not OTel replacements.

---

## Clarification Loop

When the Orchestrator's confidence score is below 0.7, it enters the **Clarification Loop** instead of routing to a sub-agent:

```
1. Orchestrator returns clarification_question to web backend
2. InfraRequest.status → clarifying
3. Web UI shows the question to the user
4. User answers → POST /requests/{infra_request_id}/clarify {answer: "..."}
5. Web backend fetches original InfraRequest from PostgreSQL (raw_input + normalized_params so far)
6. Web backend calls Orchestrator with: original raw_input + clarification answer + infra_request_id
7. Orchestrator re-runs normalisation with combined context
8. If confidence ≥ 0.7 → proceed to confirmation flow
9. If still < 0.7 → another clarification round (max 2 rounds per request)
```

The Orchestrator is stateless — it receives full context on each call. It does not maintain conversation history. The web backend reconstructs context from PostgreSQL.

**Max clarification rounds**: 2. After 2 failed rounds, the request is rejected with a message asking the user to rephrase from scratch.

**Endpoint**: `POST /requests/{infra_request_id}/clarify` — distinct from `POST /requests` (new request) and `POST /jobs/{job_id}/confirm` (confirmation).

---

## Email Channel: Clarification Not Supported

The **Clarification Loop** is only available on the `web` channel. Email requests that fall below the 0.7 confidence threshold are **rejected immediately** — no clarification email is sent.

The rejection email MUST include a specific, example-driven message:
> *"I couldn't understand your request. Please send a clearer message. Examples: 'Check the status of vm-123' or 'Create a VM with 4 CPUs in us-central1'."*

**Rationale**: The Gmail poller operates on a 30-second poll cycle. A clarification round-trip over email could take hours, and tracking which threads are awaiting clarification vs confirmation adds significant polling state complexity for Phase 1.

Users who need the interactive clarification loop should use the web UI.

---

## Naming Convention: "Enquiry" (British spelling, canonical)

The word **enquiry** (British spelling) is the canonical term across the entire codebase. This applies to all identifiers: class names, function names, variable names, module paths, database columns, PubSub topic names, Airflow DAG IDs, and documentation.

**Correct**: `enquiry_agent`, `EnquiryTask`, `enquiry_flow`, `status_enquiry_dag`
**Incorrect**: `inquiry_agent`, `InquiryTask`, `query_agent`, `search_agent`

Deviations from this convention are bugs to be caught in code review. The spell-checker underline is acceptable — the consistency is not negotiable.

---

## rollback_resources (append-after-create, not pre-planned)

`rollback_resources` on ProvisioningJob starts **empty** (`[]`). The Airflow DAG appends each resource to the list immediately after its GCP `create_*` call succeeds — before moving to the next step.

```
DAG step 1: create_vpc_network → succeeds
  → postgres-mcp.update_job_status(rollback_resources=[{type: vpc_network, name: "my-vpc", ...}])
DAG step 2: create_subnetwork → fails
  → rollback triggered
  → rollback_resources = [{type: vpc_network, name: "my-vpc", ...}]  ← only what was created
  → delete_vpc_network("my-vpc") called
```

**Never pre-populated from dry-run output.** The dry-run validates parameters only — it does not set `rollback_resources`. Setting `rollback_resources` from the dry-run plan (rather than actuals) risks attempting to delete resources that were never created, producing misleading 404 errors during rollback.

---

## Backstage Registration (hard requirement)

Backstage catalog registration is a **hard requirement** for a ProvisioningJob to reach `succeeded`. If `register_entity` fails after GCP provisioning completes, the DAG triggers rollback — deleting the provisioned GCP resources and marking the job `failed`.

**Operational implication**: A Backstage API outage will cause successfully provisioned GCP resources to be destroyed. This is an accepted trade-off — catalog accuracy is treated as a correctness invariant, not a best-effort side effect.

Mitigation: Backstage must be included in the platform's uptime SLA (99.5%). Circuit breaker on `backstage-mcp` with alerting on open state. Runbook must exist for Backstage outage recovery.

**Synonym to avoid**: Do not call Backstage registration "optional" or "best-effort" — it is neither.

---

## Daily Provisioning Limit

The developer daily provisioning limit (10 resources/day) resets at **midnight UTC** every calendar day. The reset is global — not per-user timezone, not a rolling 24-hour window.

`daily_count_reset_at` records the last midnight UTC reset timestamp. On each provisioning attempt, if `NOW() > daily_count_reset_at + INTERVAL '1 day'`, the count resets to 0 before the limit check.

The rate-limit error message MUST state the reset time explicitly: *"Your daily provisioning limit resets at midnight UTC."*

Platform engineers have no daily limit. Their `daily_provisioning_count` is not checked.

---

## Normalisation

**Normalisation** is the process of converting an unstructured natural language request into a fully resolved, GCP-typed parameter set in a single LLM pass. It performs both extraction (pulling explicit values from the user's message) and resolution (mapping vague descriptions to concrete GCP values, e.g. "4 CPUs" → `machine_type: e2-standard-4`).

When normalisation cannot resolve a parameter unambiguously, the system enters the **Clarification** step — it asks the user a targeted question — before proceeding to Confirmation.

**Normalisation flow**:
```
raw_input → [LLM normalisation pass] → resolved params
                                      ↓ if ambiguous
                                  [Clarification] → user reply → re-normalise
                                      ↓ resolved
                                  [Confirmation summary shown to user]
```

The output of normalisation is always fully resolved GCP parameters — no intermediate `cpu_count` fields. The Skill receives typed GCP values.

**Synonym to avoid**: "parsing", "extraction" (extraction is only half of what normalisation does), "interpretation"

---

## Confirmation Flow

The **Confirmation Flow** is the sequence from normalisation to PubSub publish:

```
1. Orchestrator → Provisioning Agent (normalised params, confirmed: false)
2. Provisioning Agent → creates ProvisioningJob (status: pending), returns confirmation_summary
3. Web backend → shows summary to user, starts 20-minute countdown
4. User clicks "Confirm" → POST /jobs/{job_id}/confirm → Web backend
5. Web backend → A2A call → Provisioning Agent (confirmed: true)
6. Provisioning Agent → updates InfraRequest (status: confirmed) via postgres-mcp
7. Provisioning Agent → publishes provisioning request to PubSub via pubsub-mcp
8. Airflow PubSubPullSensor fires → DAG takes ownership
```

The web backend does NOT call the Orchestrator on confirmation — it calls the Provisioning Agent directly (step 5). The Orchestrator is only involved in initial intent routing.

---

## ProvisioningJob State Machine

The canonical ProvisioningJob states are:

```
awaiting_confirmation ──(user confirms)──► queued ──► in_progress ──► succeeded
        │                                    │              │
        │                              (Airflow picks       ├──(transient failure)──► retrying ──► in_progress
        │                               up message)         │                                  └──(exhausted)──► rollback ──► failed
        │
        ├──(user cancels or 20-min timeout)──► cancelled
        └──(user rejects)──► cancelled

queued ──(user cancels before Airflow picks up)──► cancelled
```

**`awaiting_confirmation`**: ProvisioningJob exists, confirmation summary shown to user. Cancellable. 20-minute timeout applies. Human is the blocker.

**`queued`**: User confirmed. PubSub message published. Airflow PubSubPullSensor has not yet fired. No longer cancellable via normal flow. Infrastructure is the blocker (10–30 second window).

**`in_progress`**: Airflow DAG has picked up the message and is executing GCP API calls.

**`retrying`**: A task within the DAG failed transiently. Exponential backoff with jitter applies. Retry count ≤ 3.

**`rollback`**: Retries exhausted. DAG is deleting successfully created resources before reporting failure.

**`succeeded`**: All GCP resources created, Backstage registered, status event published.

**`failed`**: Rollback complete. All created resources deleted.

**`cancelled`**: User cancelled from `awaiting_confirmation` or `queued` state.

**Impact on contracts**: `job_status` enum in PostgreSQL schema, PubSub status event `status` field, and web API job status response all use these canonical values. The old `pending` state is retired — use `awaiting_confirmation` or `queued`.

---

## ProvisioningJob (state authority)

The **Airflow DAG** is the single authoritative writer of ProvisioningJob state in PostgreSQL (via the `postgres-mcp`). It writes state at each transition, which triggers PostgreSQL LISTEN/NOTIFY, which drives SSE to the browser.

The **notification service** subscribes to the PubSub status topic for email delivery only. It never writes to PostgreSQL.

This means ProvisioningJob state in PostgreSQL is always consistent with what Airflow has actually done — there is no dual-write race between a PubSub subscriber and a DAG.

---
