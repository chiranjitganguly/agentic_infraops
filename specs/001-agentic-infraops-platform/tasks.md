# Tasks: Agentic InfraOps Self-Service Platform (Phase 1)

**Input**: Design documents from `specs/001-agentic-infraops-platform/`
**Branch**: `001-agentic-infraops-platform`
**Generated**: 2026-05-10

**Domain corrections applied** (from `CONTEXT.md` and ADRs 0001–0006):
- Channel enum uses `web` (not `chatbot`)
- ProvisioningJob states: `awaiting_confirmation` + `queued` (not `pending`)
- `rollback_resources` starts empty, appended after each successful GCP create
- Backstage registration is a hard requirement for job success
- Confirmation click → web backend → Provisioning Agent (not Orchestrator)
- Email channel rejects low-confidence requests (no clarification loop)
- Clarification endpoint: `POST /requests/{infra_request_id}/clarify`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to
- Tests are included per the constitution (XIV. Testing & Agent Evaluation Standards)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Monorepo scaffolding, Docker Compose stack, Python packaging, CI/CD gates

- [x] T001 Create monorepo directory structure per plan.md (`agents/`, `skills/`, `mcp_servers/`, `workflows/`, `contracts/`, `web/`, `evaluations/`, `infrastructure/`, `docker/`, `observability/`, `docs/`, `tests/`)
- [x] T002 [P] Initialise Python package structure — create `pyproject.toml` for each package: `agents/orchestrator`, `agents/provisioning`, `agents/enquiry`, `agents/faq`, `skills/intent_classification`, `skills/gcp_compute`, `skills/gcp_storage`, `skills/gcp_network`, `skills/status_query`, `skills/document_retrieval`
- [x] T003 [P] Initialise Python package structure for MCP servers — create `pyproject.toml` for each: `mcp_servers/gcp_resource`, `mcp_servers/knowledge_base`, `mcp_servers/postgres`, `mcp_servers/pubsub`, `mcp_servers/airflow`, `mcp_servers/backstage`, `mcp_servers/gmail`
- [x] T004 [P] Write `docker/docker-compose.yml` defining all services: `postgres`, `qdrant`, `pubsub-emulator`, `litellm`, `airflow-webserver`, `airflow-scheduler`, `airflow-worker`, `orchestrator-agent`, `provisioning-agent`, `enquiry-agent`, `faq-agent`, `web-backend`, `web-frontend`, `gmail-poller`, `notification-service`, `prometheus`, `grafana`
- [x] T005 [P] Write `docker/services/` Dockerfiles for each service (one per agent, one per MCP server, one for web-backend, one for gmail-poller, one for notification-service)
- [x] T006 [P] Write `.env.example` with all required environment variables per `quickstart.md`
- [x] T007 [P] Configure Ruff (linting) and Black (formatting) — create `pyproject.toml` at repo root with `[tool.ruff]` and `[tool.black]` sections
- [x] T008 [P] Set up CI/CD scaffolding — create `.github/workflows/ci.yml` with gates: lint, type-check, unit tests, contract tests, schema validation
- [x] T009 [P] Write `infrastructure/scripts/migrate.py` — PostgreSQL migration runner (applies SQL files in `infrastructure/db/migrations/` in order)
- [x] T010 [P] Write `infrastructure/scripts/seed_knowledge_base.py` — chunks and indexes Markdown files from `docs/knowledge/` into Qdrant collection `infraops_knowledge_base`
- [x] T011 [P] Write `infrastructure/scripts/create_user.py` — creates a `UserRole` row, generates and prints a plaintext API key (bcrypt-hashed before storage)
- [x] T012 [P] Write `observability/prometheus/prometheus.yml` and `observability/grafana/dashboards/` with basic InfraOps dashboard (job status counts, intent classification latency, circuit breaker states)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: PostgreSQL schema, shared Pydantic contracts, structured logging, auth middleware, PubSub topic initialisation, LiteLLM config. MUST be complete before any user story work begins.

**⚠️ CRITICAL**: No user story tasks can begin until this phase is complete.

### Database Schema

- [x] T013 Write PostgreSQL schema migration `infrastructure/db/migrations/001_initial_schema.sql` — creates all enums (`channel_type`, `intent_type`, `request_status`, `job_status`, `resource_type_enum`, `user_role_type`), tables (`infra_requests`, `provisioning_jobs`, `faq_queries`, `audit_events`, `user_roles`), indexes, and the `updated_at` trigger function per `data-model.md`. Use `awaiting_confirmation` and `queued` in `job_status` enum (not `pending`).
- [x] T014 Write PostgreSQL migration `infrastructure/db/migrations/002_notify_trigger.sql` — creates `notify_job_status_change()` trigger function and attaches it to `provisioning_jobs.status` updates (drives SSE via LISTEN/NOTIFY)
- [x] T015 Write PostgreSQL migration `infrastructure/db/migrations/003_immutable_audit.sql` — creates `no_update_audit_events` and `no_delete_audit_events` rules on `audit_events` table

### Shared Pydantic Contract Models

- [x] T016 [P] Create `contracts/schemas/infra_request.py` — Pydantic v2 models: `InfraRequestCreate`, `InfraRequest`, `InfraRequestStatus` enum (all states from `data-model.md`), `ChannelType` enum with `web` and `email` values
- [x] T017 [P] Create `contracts/schemas/provisioning_job.py` — Pydantic v2 models: `ProvisioningJobCreate`, `ProvisioningJob`, `JobStatus` enum (`awaiting_confirmation`, `queued`, `in_progress`, `retrying`, `rollback`, `succeeded`, `failed`, `cancelled`), `ResourceType` enum, `RollbackResource` model
- [x] T018 [P] Create `contracts/schemas/user_role.py` — Pydantic v2 models: `UserRole`, `UserRoleType` enum (`developer`, `platform_engineer`), `DeveloperGuardrails` (allowed regions, machine types, storage classes)
- [x] T019 [P] Create `contracts/schemas/audit_event.py` — Pydantic v2 models: `AuditEventCreate`, `AuditEvent`, `AuditEventType` enum (all 21 event types from `data-model.md`)
- [x] T020 [P] Create `contracts/schemas/faq_query.py` — Pydantic v2 models: `FAQQueryCreate`, `FAQQuery`, `RetrievedChunk`
- [x] T021 [P] Create `contracts/events/pubsub_events.py` — Pydantic v2 models for all PubSub message schemas: `ProvisioningRequestEvent`, `ProvisioningStatusEvent`, `AuditEventMessage` per `contracts/pubsub-events.md` schema v1.0.0
- [x] T022 [P] Create `contracts/agents/orchestrator.py` — Pydantic v2 models: `OrchestratorInput`, `OrchestratorOutput`, `Outcome` enum per `contracts/a2a-agents.md`
- [x] T023 [P] Create `contracts/agents/provisioning.py` — Pydantic v2 models: `ProvisioningInput`, `ProvisioningConfirmationOutput`, `ProvisioningQueuedOutput`, `ProvisioningErrorOutput`, `VMParameters`, `BucketParameters`, `VPCParameters` per `contracts/a2a-agents.md`
- [x] T024 [P] Create `contracts/agents/enquiry.py` — Pydantic v2 models: `EnquiryInput`, `EnquiryFoundOutput`, `EnquiryNotFoundOutput`, `EnquiryAccessDeniedOutput` per `contracts/a2a-agents.md`
- [x] T025 [P] Create `contracts/agents/faq.py` — Pydantic v2 models: `FAQInput`, `FAQAnsweredOutput`, `FAQNoResultsOutput`, `Source` per `contracts/a2a-agents.md`

### Shared Infrastructure Packages

- [x] T026 [P] Create `contracts/shared/logging.py` — structured logging setup using `structlog`; configures JSON output with mandatory fields: `correlation_id`, `request_id`, `agent_name`, `workflow_name`, `timestamp`; sensitive field redaction (`api_key`, `api_key_hash`, `password`, `token`)
- [x] T027 [P] Create `contracts/shared/correlation.py` — `CorrelationContext` dataclass and context-var-based propagation helpers; `inject_correlation_headers()` and `extract_correlation_headers()` for A2A HTTP calls
- [x] T028 [P] Create `contracts/shared/metrics.py` — Prometheus metrics registry shared across all services: `provisioning_job_total`, `intent_classification_duration_seconds`, `circuit_breaker_state`, `api_request_duration_seconds`
- [x] T029 Create `contracts/shared/circuit_breaker.py` — `@circuit_breaker(failure_threshold=5, recovery_timeout=60)` decorator wrapping the `circuitbreaker` library; exposes circuit state as Prometheus gauge; raises `CircuitOpenError` when open
- [x] T030 [P] Create `infrastructure/db/connection.py` — `asyncpg` connection pool factory; reads `DATABASE_URL` from environment; exposes `get_pool()` async context manager
- [x] T031 Write `infrastructure/pubsub/setup.py` — creates PubSub topics and subscriptions on startup if they do not exist: `infraops.provisioning.requests` + subscription `infraops-provisioning-requests-vm-sub` and `infraops-provisioning-requests-bucket-sub`; `infraops.provisioning.status` + subscription `infraops-provisioning-status-sub`; `infraops.audit.events` + subscription `infraops-audit-events-sub`
- [x] T032 Write `docker/services/litellm/litellm_config.yaml` — LiteLLM proxy config per `research.md`: Gemini default model, embedding model, master key from env, retry/fallback settings, Prometheus metrics at `/metrics`

**Checkpoint**: Foundation complete. User story phases can now begin in parallel.

---

## Phase 3: User Story 1 — Self-Service VM Provisioning (Priority: P1) 🎯 MVP

**Goal**: A user submits a natural language VM provisioning request via web UI or email. The system normalises it, asks for clarification if ambiguous, shows a confirmation summary, the user confirms, Airflow provisions the VM in GCP, and the user sees live status via SSE.

**Independent Test**: `curl -X POST /api/v1/requests -d '{"raw_input": "Create a VM with 4 CPUs in us-central1", "channel": "web"}' -H "X-API-Key: ..."` → receive `job_id` + `confirmation_summary` → confirm → SSE stream shows `in_progress` → `succeeded` with `gcp_resource_id`.

### Contract Tests (write first, verify they FAIL before implementation)

- [ ] T033 [P] [US1] Write contract test for `ProvisioningRequestEvent` schema in `tests/contract/test_pubsub_provisioning_event.py` — validates all required fields, `schema_version: "1.0.0"`, `job_status` values exclude `pending`
- [ ] T034 [P] [US1] Write contract test for `POST /requests` web API in `tests/contract/test_web_api_requests.py` — validates 202 response schema, `awaiting_confirmation` status, confirmation_summary non-null for provision intent
- [ ] T035 [P] [US1] Write contract test for Orchestrator A2A input/output in `tests/contract/test_a2a_orchestrator.py` — validates `OrchestratorInput`, `OrchestratorOutput`, `Outcome` enum values

### MCP Servers (US1 dependencies)

- [ ] T036 [P] [US1] Implement `mcp_servers/postgres/server.py` — MCP server wrapping all PostgreSQL tools per `contracts/mcp-servers.md`: `get_provisioning_job`, `get_provisioning_job_by_idempotency_key`, `create_provisioning_job`, `update_job_status` (includes pg_notify call), `cancel_job`, `get_infra_request`, `create_infra_request`, `update_request_status`, `get_user_role`, `verify_api_key`, `get_daily_usage_count`, `increment_daily_usage`, `create_audit_event`
- [ ] T037 [P] [US1] Implement `mcp_servers/pubsub/server.py` — MCP server wrapping PubSub publish: `publish_provisioning_request`, `publish_status_event`, `publish_audit_event`; auto-detects `PUBSUB_EMULATOR_HOST` for local dev
- [ ] T038 [P] [US1] Implement `mcp_servers/gcp_resource/server.py` (VM subset) — MCP server tools: `create_vm` (with `dry_run` parameter), `delete_vm` (rollback), `get_vm_status`; all wrapped with `@circuit_breaker` from `contracts/shared/circuit_breaker.py`
- [ ] T039 [P] [US1] Implement `mcp_servers/backstage/server.py` — MCP server wrapping Backstage catalog API: `register_entity`, `update_entity`, `get_entity` per `contracts/mcp-servers.md`; wrapped with `@circuit_breaker`
- [ ] T040 [P] [US1] Implement `mcp_servers/gmail/server.py` — MCP server tools: `poll_unread_messages` (uses `history.list()` incremental sync per `research.md`), `get_message`, `get_thread_messages`, `send_email`, `mark_as_read`, `is_auto_reply`

### Skills (US1 dependencies)

- [ ] T041 [P] [US1] Implement `skills/intent_classification/classifier.py` — `classify(raw_input: str, channel: ChannelType) -> ClassificationResult` using LiteLLM (via gateway); returns `intent`, `confidence`, `normalized_params`; uses structured output / function calling to produce typed `VMParameters | BucketParameters | VPCParameters | EnquiryParams | FAQParams`; includes normalisation (extraction + resolution in one pass per `CONTEXT.md`)
- [ ] T042 [US1] Implement `skills/gcp_compute/provisioner.py` — `create_vm(params: VMParameters, dry_run: bool) -> ProvisionResult`; calls `gcp-resource-mcp` `create_vm`; on success appends to `rollback_resources` via `postgres-mcp` `update_job_status`; on `dry_run=True` validates without GCP call; wrapped with `@circuit_breaker`
- [ ] T043 [US1] Implement `skills/gcp_compute/rollback.py` — `rollback_vm(rollback_resources: list[RollbackResource]) -> RollbackResult`; iterates `rollback_resources`, calls `gcp-resource-mcp` `delete_vm` for each; ignores 404 responses; logs each delete attempt
- [ ] T044 [US1] Implement `skills/gcp_compute/guardrails.py` — `validate_developer_guardrails(params: VMParameters, user_role: UserRoleType) -> GuardrailResult`; checks region against `DeveloperGuardrails.allowed_regions`, machine_type against `DeveloperGuardrails.allowed_machine_types`; returns `GuardrailViolation` if outside bounds

### Agents (US1)

- [ ] T045 [US1] Implement `agents/orchestrator/agent.py` — Google ADK agent with A2A task handler; on `POST /tasks`: calls `intent_classification` skill; if `confidence < 0.7` returns `clarification_needed` outcome; if `provision` intent + developer role calls `validate_developer_guardrails`; if guardrail violation returns `guardrail_violation` outcome; calls `increment_daily_usage` via `postgres-mcp`; on success routes to Provisioning Agent via A2A; exposes `/.well-known/agent.json` agent card
- [ ] T046 [US1] Implement `agents/orchestrator/clarification.py` — `build_clarification_question(top_intents: list[IntentCandidate]) -> str`; formats top-2 intent candidates as a user-facing question; used when confidence < 0.7
- [ ] T047 [US1] Implement `agents/provisioning/agent.py` — Google ADK agent with A2A task handler; on `POST /tasks` with `confirmed=False`: checks idempotency via `postgres-mcp` `get_provisioning_job_by_idempotency_key`; creates `ProvisioningJob` with status `awaiting_confirmation`; returns confirmation summary; on `POST /tasks` with `confirmed=True`: updates `InfraRequest` status to `confirmed`, updates `ProvisioningJob` status to `queued`, publishes `ProvisioningRequestEvent` to PubSub via `pubsub-mcp`; emits audit events via `postgres-mcp` `create_audit_event`; exposes `/.well-known/agent.json`
- [ ] T048 [US1] Implement `agents/provisioning/confirmation.py` — `build_confirmation_summary(params: VMParameters, defaults_applied: dict) -> str`; human-readable summary of what will be created including any defaults the system applied; includes 20-minute expiry warning

### Airflow DAG (US1)

- [ ] T049 [US1] Implement `workflows/dags/provision_vm_dag.py` — Airflow DAG `provision_vm_dag` with tasks:
  1. `wait_for_message`: `PubSubPullSensor` on `infraops-provisioning-requests-vm-sub`, filters `resource_type == compute_instance`
  2. `update_in_progress`: calls `postgres-mcp` `update_job_status(status=in_progress)`; publishes `in_progress` status event
  3. `dry_run_validate`: calls `gcp_compute` skill `create_vm(dry_run=True)`; fails fast on validation error
  4. `provision_vm`: calls `gcp_compute` skill `create_vm(dry_run=False)`; on success appends to `rollback_resources` via `postgres-mcp`
  5. `register_backstage`: calls `backstage-mcp` `register_entity`; on failure → triggers rollback group (ADR 0005)
  6. `update_succeeded`: calls `postgres-mcp` `update_job_status(status=succeeded)`; publishes `succeeded` status event
  - `rollback_group` (TriggerRule.ONE_FAILED): `rollback_vm` (calls `gcp_compute` rollback skill) → `update_failed` (status=failed + publishes failed event)
  - Retry policy on `provision_vm`: 3 retries, exponential backoff with jitter per `research.md`; on each retry publishes `retrying` status event and updates `retry_count` via `postgres-mcp`

### Web Backend (US1)

- [ ] T050 [US1] Implement `web/backend/main.py` — FastAPI app with API key auth middleware (`X-API-Key` header → `postgres-mcp` `verify_api_key`); mounts routers; configures CORS; starts `asyncpg` pool on startup
- [ ] T051 [US1] Implement `web/backend/middleware/auth.py` — FastAPI middleware: extracts `X-API-Key`, calls `postgres-mcp` `verify_api_key`, attaches `UserRole` to request state; rejects with 401 on invalid/expired key; brute-force protection: 5 failed attempts/IP/minute → 429
- [ ] T052 [US1] Implement `web/backend/routers/requests.py` — `POST /api/v1/requests`: validates body, calls Orchestrator Agent via A2A; handles `clarification_needed` (returns 202 with question), `guardrail_violation` (400), `rate_limited` (429), `routed` (passes confirmation summary back); `POST /api/v1/requests/{infra_request_id}/clarify`: fetches InfraRequest from `postgres-mcp`, reconstructs context, calls Orchestrator with combined input; max 2 clarification rounds per request
- [ ] T053 [US1] Implement `web/backend/routers/jobs.py` — `POST /api/v1/jobs/{job_id}/confirm`: calls Provisioning Agent via A2A with `confirmed=True`; `POST /api/v1/jobs/{job_id}/cancel`: updates `ProvisioningJob` to `cancelled` via `postgres-mcp` (only from `awaiting_confirmation` or `queued`); `GET /api/v1/jobs/{job_id}`: returns current job status; `GET /api/v1/jobs`: list jobs with filters
- [ ] T054 [US1] Implement `web/backend/routers/sse.py` — `GET /api/v1/jobs/{job_id}/stream`: opens `asyncpg` connection, calls `LISTEN infraops_job_status`, streams SSE events on each NOTIFY payload matching `job_id`; sends `event: done` and closes stream on terminal status (`succeeded`, `failed`, `cancelled`); uses `sse-starlette` `EventSourceResponse`
- [ ] T055 [US1] Implement `web/backend/routers/auth.py` — `GET /api/v1/auth/me`: returns user info + daily count; `POST /api/v1/auth/rotate-key`: generates new key, bcrypt-hashes it, stores in `postgres-mcp`, returns plaintext once

### Gmail Poller (US1 — email provisioning path)

- [ ] T056 [US1] Implement `web/backend/gmail_poller/poller.py` — async polling loop (30-second interval); calls `gmail-mcp` `poll_unread_messages` with stored `history_id`; for each message: calls `is_auto_reply` — skip if true; calls `get_thread_messages` to check if thread has a sent confirmation (awaiting confirmation reply) or is a new top-level request; dispatches accordingly; marks as read via `gmail-mcp`
- [ ] T057 [US1] Implement `web/backend/gmail_poller/dispatcher.py` — `dispatch_email_request(message: GmailMessage) -> None`: all email requests use `user_role = developer` (per grill-me Q8); calls Orchestrator A2A; if `confidence < 0.7` → sends rejection email via `gmail-mcp` `send_email` with example-driven message (per `CONTEXT.md`); if valid → sends confirmation email with 20-minute deadline; `dispatch_confirmation_reply(message: GmailMessage, infra_request_id: UUID) -> None`: calls Provisioning Agent A2A with `confirmed=True`

### Notification Service (US1)

- [ ] T058 [US1] Implement `web/backend/notification_service/service.py` — subscribes to `infraops-provisioning-status-sub` PubSub subscription; on each `ProvisioningStatusEvent`: sends status update email to `requesting_user` via `gmail-mcp` `send_email`; deduplicates by `(job_id, status)` using an in-memory set; does NOT write to PostgreSQL (per ADR 0003)

### Integration Tests (US1)

- [ ] T059 [US1] Write integration test `tests/integration/test_vm_provisioning_flow.py` — end-to-end: submit provision request → get confirmation summary → confirm → assert job transitions through `awaiting_confirmation → queued → in_progress → succeeded`; uses PubSub emulator and stubbed GCP API; verifies `rollback_resources` is empty before first GCP call and populated after

**Checkpoint**: Submit "Create a VM with 4 CPUs in us-central1" via web UI → confirm → SSE stream shows succeeded. Email path: send email → receive confirmation email → reply "confirm" → receive success email. User Story 1 fully functional.

---

## Phase 4: User Story 2 — Self-Service Storage Bucket Provisioning (Priority: P1)

**Goal**: Extend the provisioning pipeline with bucket provisioning. Same confirmation flow and DAG pattern as US1 but for Cloud Storage buckets.

**Independent Test**: `curl -X POST /api/v1/requests -d '{"raw_input": "Create a storage bucket named my-data-bucket in us-east1", "channel": "web"}' -H "X-API-Key: ..."` → confirm → SSE shows `succeeded` with bucket `gcp_resource_id`.

### Contract Tests

- [ ] T060 [P] [US2] Write contract test for bucket `ProvisioningRequestEvent` in `tests/contract/test_pubsub_bucket_event.py` — validates `resource_type: storage_bucket`, `BucketParameters` schema, `storage_class` enum values

### MCP Servers (US2 additions)

- [ ] T061 [P] [US2] Extend `mcp_servers/gcp_resource/server.py` — add `create_bucket` (with `dry_run`), `delete_bucket` (rollback), `get_bucket_status` tools per `contracts/mcp-servers.md`

### Skills (US2)

- [ ] T062 [P] [US2] Implement `skills/gcp_storage/provisioner.py` — `create_bucket(params: BucketParameters, dry_run: bool) -> ProvisionResult`; calls `gcp-resource-mcp` `create_bucket`; on success appends to `rollback_resources`; validates `BucketParameters` (bucket name regex, storage class enum); wrapped with `@circuit_breaker`
- [ ] T063 [P] [US2] Implement `skills/gcp_storage/rollback.py` — `rollback_bucket(rollback_resources: list[RollbackResource]) -> RollbackResult`; calls `gcp-resource-mcp` `delete_bucket` for each; ignores 404
- [ ] T064 [P] [US2] Implement `skills/gcp_storage/guardrails.py` — `validate_developer_guardrails(params: BucketParameters, user_role: UserRoleType) -> GuardrailResult`; checks `storage_class` against `DeveloperGuardrails.allowed_storage_classes`

### Airflow DAG (US2)

- [ ] T065 [US2] Implement `workflows/dags/provision_bucket_dag.py` — Airflow DAG `provision_bucket_dag` following same structure as `provision_vm_dag`: `PubSubPullSensor` (filters `resource_type == storage_bucket`) → `dry_run_validate` → `provision_bucket` (appends to `rollback_resources` on success) → `register_backstage` (hard requirement per ADR 0005) → `update_succeeded`; same rollback group pattern; same retry policy

### Agents (US2 extension)

- [ ] T066 [US2] Extend `agents/provisioning/agent.py` — add `BucketParameters` handling branch; bucket confirmation summary via `build_confirmation_summary`; same idempotency key logic (`resource_type + name + region`)

### Integration Tests (US2)

- [ ] T067 [US2] Write integration test `tests/integration/test_bucket_provisioning_flow.py` — end-to-end bucket provisioning including Backstage registration failure scenario: assert that when `backstage-mcp` `register_entity` fails, rollback deletes the bucket and job status becomes `failed`

**Checkpoint**: Both VM and bucket provisioning work end-to-end. User Stories 1 and 2 independently testable.

---

## Phase 5: User Story 3 — Infrastructure Status Enquiry (Priority: P2)

**Goal**: A user asks "What is the status of vm-123?" or "List all my VMs" via web UI or email. The system queries GCP live and returns structured metadata + a human-readable summary within 30 seconds.

**Independent Test (single)**: `curl -X POST /api/v1/requests -d '{"raw_input": "What is the status of vm-123?", "channel": "web"}' -H "X-API-Key: ..."` → immediate 200 with `gcp_status`, typed `metadata` object, `human_readable_summary`.

**Independent Test (list)**: `curl -X POST /api/v1/requests -d '{"raw_input": "List all my VMs", "channel": "web"}' -H "X-API-Key: ..."` → immediate 200 with `resources[]` array and `total_count`.

**Direct REST test**: `curl "http://localhost:8000/api/v1/resources/compute_instance/vm-123?project_id=agentic-infraops&zone=us-central1-a" -H "X-API-Key: ..."` → 200 with typed metadata.

### Contract Tests

- [x] T068 [P] [US3] Write contract test for Enquiry Agent A2A in `tests/contract/test_a2a_enquiry.py` — validates `EnquiryInput` (`query_type` field present, `resource_name` nullable), `EnquiryFoundOutput` (`gcp_status`, typed `metadata` matching one of `VMMetadata | BucketMetadata | VPCMetadata`, `human_readable_summary`, `queried_at`), `EnquiryListOutput` (`resources[]`, `total_count`), `EnquiryNotFoundOutput`, `EnquiryAccessDeniedOutput` schemas
- [x] T068a [P] [US3] Write contract test for typed metadata models in `tests/contract/test_resource_metadata.py` — validates `VMMetadata`, `BucketMetadata`, `VPCMetadata`, `ResourceSummary` Pydantic models import and validate cleanly against sample GCP API response fixtures

### MCP Servers (US3 additions)

- [x] T069 [P] [US3] Extend `mcp_servers/gcp_resource/server.py` — add `get_vpc_status` tool and `list_project_resources` tool; `list_project_resources` returns `[ResourceSummary]` with `resource_name`, `gcp_status`, `zone_or_region`, `key_metadata`, `creation_timestamp`; ensure all status tools wrapped with `@circuit_breaker`

### Skills (US3)

- [x] T070 [P] [US3] Implement `skills/status_query/querier.py` — two functions: (1) `query_resource_status(resource_type, resource_name, project_id, zone, region) -> ResourceStatus` — calls appropriate `gcp-resource-mcp` status tool, deserialises raw GCP response into typed `VMMetadata | BucketMetadata | VPCMetadata`; (2) `list_resources(resource_type, project_id) -> list[ResourceSummary]` — calls `list_project_resources` MCP tool; both wrapped with `@circuit_breaker`
- [x] T071 [P] [US3] Implement `skills/status_query/formatter.py` — `format_status_response(metadata: VMMetadata | BucketMetadata | VPCMetadata, gcp_status: str, resource_type: ResourceType) -> str`; per-type templates: VM → "{name} is {status} in {zone} ({machine_type})"; bucket → "{name}: {storage_class} in {location}, versioning {'on' if versioning_enabled else 'off'}"; VPC → "{name} is {status}, {subnet_count} subnet(s), routing {routing_mode}"; `format_list_response(resources: list[ResourceSummary], resource_type: ResourceType) -> str` → tabular summary

### Agent (US3)

- [x] T072 [US3] Implement `agents/enquiry/agent.py` — Google ADK agent; on `POST /tasks` with `EnquiryInput`: routes to `query_resource_status` (query_type=single) or `list_resources` (query_type=list); handles `found`, `not_found`, `access_denied`, `listed` outcomes; emits `status_queried` audit event via `postgres-mcp`; exposes `/.well-known/agent.json`
- [x] T073 [US3] Extend `agents/orchestrator/agent.py` — add `enquiry` intent routing branch: detect `query_type` from `normalized_params` (`list` when resource_name is absent/null, `single` otherwise); extract `resource_type`, `resource_name`, `project_id`; call Enquiry Agent via A2A; return result immediately (no confirmation flow)

### Web Backend (US3 extension)

- [x] T074 [US3] Extend `web/backend/routers/requests.py` — handle `enquiry` intent in `POST /api/v1/requests`: return 200 immediately with full structured response (`query_type`, `resource_type`, `gcp_status`, typed `metadata`, `answer`, `queried_at` for single; `resources[]`, `total_count`, `answer`, `queried_at` for list)
- [x] T074a [US3] Add `GET /api/v1/resources/{resource_type}/{resource_name}` endpoint to `web/backend/routers/resources.py` — direct GCP status lookup bypassing NL classification; calls `status_query` skill directly; returns typed `ResourceStatus` response; auth required
- [x] T074b [US3] Add `GET /api/v1/resources` endpoint — direct project resource listing; calls `list_resources` skill; query params: `resource_type` (required), `project_id` (optional, defaults to env), `limit`, `offset`; returns `ResourceSummary[]`

### Integration Tests (US3)

- [x] T075 [US3] Write integration test `tests/integration/test_enquiry_flow.py` — tests: (1) single resource found — validate `gcp_status`, `metadata` fields match resource type schema, `human_readable_summary` non-empty; (2) resource not found → 404-style answer; (3) access denied scenario; (4) list query → `resources[]` non-empty, `total_count` correct; (5) direct `GET /resources/{type}/{name}` → typed metadata; validates all responses within 30-second SLA; validates `status_queried` audit event written to PostgreSQL

**Checkpoint**: "What is the status of vm-123?" returns `gcp_status` + typed metadata within 30 seconds. "List all my VMs" returns a resource list. `GET /api/v1/resources` works independently. User Story 3 fully independently testable.

---

## Phase 6: User Story 4 — Best-Practice FAQ Responses (Priority: P3)

**Goal**: A user asks "What is the best practice for VPC design on GCP?" The system retrieves from the Qdrant knowledge base using hybrid search and returns a cited answer within 60 seconds.

**Independent Test**: `curl -X POST /api/v1/requests -d '{"raw_input": "What is the best practice for VPC design on GCP?", "channel": "web"}' -H "X-API-Key: ..."` → 200 response with `answer`, `sources` list, non-empty `sources_cited`.

### Contract Tests

- [x] T076 [P] [US4] Write contract test for FAQ Agent A2A in `tests/contract/test_a2a_faq.py` — validates `FAQInput`, `FAQAnsweredOutput` (has non-empty `answer` and `sources`), `FAQNoResultsOutput` schemas

### MCP Servers (US4)

- [x] T077 [P] [US4] Implement `mcp_servers/knowledge_base/server.py` — MCP server wrapping Qdrant: `search_documents` (hybrid BM25 + dense vector via Qdrant's built-in FastEmbed sparse + dense, RRF fusion, `score_threshold=0.5`), `get_document_by_id`, `index_document`, `get_collection_stats`; embedding model called via LiteLLM gateway

### Skills (US4)

- [x] T078 [P] [US4] Implement `skills/document_retrieval/retriever.py` — `retrieve(question: str, top_k: int = 5) -> list[RetrievedChunk]`; calls `knowledge-base-mcp` `search_documents`; returns empty list if no chunks above `score_threshold`; each chunk includes `chunk_text`, `source_doc`, `bm25_score`, `vector_score`, `final_score`
- [x] T079 [P] [US4] Implement `skills/document_retrieval/answer_generator.py` — `generate_answer(question: str, chunks: list[RetrievedChunk]) -> FAQAnswerResult`; calls LiteLLM via gateway with retrieved chunks as context; prompt instructs model to cite sources and refuse to answer if chunks are not relevant; returns `answer`, `sources_cited`, `confidence`

### Agent (US4)

- [x] T080 [US4] Implement `agents/faq/agent.py` — Google ADK agent; on `POST /tasks` with `FAQInput`: calls `document_retrieval` skill `retrieve`; if empty chunks returns `FAQNoResultsOutput`; calls `answer_generator`; stores `FAQQuery` record via `postgres-mcp` `create_faq_query`; emits `faq_answered` audit event; exposes `/.well-known/agent.json`
- [x] T081 [US4] Extend `agents/orchestrator/agent.py` — add `faq` intent routing branch: passes question to FAQ Agent via A2A; returns result immediately

### Web Backend (US4 extension)

- [x] T082 [US4] Extend `web/backend/routers/requests.py` — handle `faq` intent in `POST /api/v1/requests`: return 200 immediately with `answer` and `sources` (no `job_id`, no SSE)

### Evaluation (US4)

- [x] T083 [US4] Create `evaluations/datasets/faq_evaluation.jsonl` — 50 Q&A pairs with GCP infrastructure best-practice questions, expected answers, and required source documents; covers VPC design, IAM, storage, compute, networking
- [x] T084 [US4] Implement `evaluations/faq/evaluate.py` — runs FAQ agent against `faq_evaluation.jsonl`; checks: answer non-empty, sources non-empty, answer does not contradict source content (hallucination check via LiteLLM judge prompt); reports pass rate; fails if < 80% of answers are grounded

### Integration Tests (US4)

- [x] T085 [US4] Write integration test `tests/integration/test_faq_flow.py` — tests: question with matching docs (returns cited answer), question with no matching docs (returns `no_results`), validates `FAQQuery` row written to PostgreSQL, validates `faq_answered` audit event

**Checkpoint**: FAQ questions return cited, grounded answers within 60 seconds. All four user stories independently functional.

---

## Phase 7: VPC Provisioning (Platform Engineer Only)

**Goal**: Extend provisioning pipeline with basic VPC network + subnet creation. Platform engineers only (developers blocked by guardrail).

**Independent Test**: Platform engineer submits "Create a VPC network named my-vpc with subnet 10.0.0.0/24 in us-central1" → confirm → DAG provisions VPC + subnet → succeeded.

- [x] T086 [P] Extend `mcp_servers/gcp_resource/server.py` — add `create_vpc_network`, `create_subnetwork`, `delete_vpc_network` tools per `contracts/mcp-servers.md`
- [x] T087 [P] Implement `skills/gcp_network/provisioner.py` — `create_vpc(params: VPCParameters, dry_run: bool) -> ProvisionResult`; calls `gcp-resource-mcp` `create_vpc_network` then `create_subnetwork`; appends each created resource to `rollback_resources` after each successful call (ADR 0006)
- [x] T088 [P] Implement `skills/gcp_network/rollback.py` — rollback in reverse order: delete subnet first, then VPC network; ignores 404
- [x] T089 Implement `workflows/dags/provision_vpc_dag.py` — same structure as VM/bucket DAGs; `PubSubPullSensor` filters `resource_type == vpc_network`; validates platform_engineer role before execution; same rollback group and Backstage registration hard requirement
- [x] T090 Extend `agents/provisioning/agent.py` — add `VPCParameters` handling branch; guardrail check: reject if `user_role == developer` with `GuardrailViolation`

---

## Phase 8: Evaluation, Observability & Testing Polish

**Purpose**: Intent classification evaluation, circuit breaker observability, end-to-end load testing, Backstage catalog entries.

### Evaluation

- [x] T091 [P] Create `evaluations/datasets/intent_classification.jsonl` — 100 labelled examples across `provision`, `enquiry`, `faq` intents; includes edge cases (ambiguous, multi-intent, email-style, overly terse)
- [x] T092 [P] Implement `evaluations/intent_classification/evaluate.py` — runs `intent_classification` skill against dataset; reports accuracy per intent class; fails if overall accuracy < 90% (SC-002); outputs confusion matrix
- [x] T093 [P] Implement `evaluations/intent_classification/evaluate_clarification.py` — runs classifier on ambiguous examples; verifies `confidence < 0.7` triggers clarification outcome; verifies high-confidence examples do not incorrectly trigger clarification

### Observability

- [x] T094 [P] Add Prometheus metrics instrumentation to all four agents — `intent_classification_duration_seconds`, `a2a_task_duration_seconds`, `a2a_task_total{outcome}` labelled by agent and outcome
- [x] T095 [P] Add circuit breaker state metrics to all `mcp_servers/gcp_resource` tools — `circuit_breaker_state{tool}` gauge (0=closed, 1=half-open, 2=open); alert rule in `observability/prometheus/rules.yml` when any circuit opens
- [x] T096 [P] Add Backstage catalog entries for all agents and skills — create `docs/backstage/` with `catalog-info.yaml` files for `orchestrator-agent`, `provisioning-agent`, `enquiry-agent`, `faq-agent` and all 6 skill packages

### Load Testing

- [x] T097 Write `tests/integration/test_concurrent_load.py` — submits 50 concurrent provisioning requests (mix of VM and bucket) via web API; asserts all requests receive `job_id`; asserts no duplicate resources created (idempotency); asserts system remains responsive (< 30s for status enquiry during load)

### Documentation

- [x] T098 [P] Write `docs/runbooks/backstage-outage.md` — runbook for Backstage API outage: how to identify jobs that were rolled back due to Backstage failure, how to manually register resources, how to resubmit after Backstage recovery (required by ADR 0005)
- [x] T099 [P] Write `docs/runbooks/circuit-breaker.md` — runbook for open circuit breaker: how to identify which GCP API is failing, how to manually reset the circuit, escalation path
- [x] T100 [P] Validate `quickstart.md` end-to-end — run all commands in `quickstart.md` against the Docker Compose stack; fix any discrepancies found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — BLOCKS all user story phases
- **Phase 3 (US1 VM)**: Depends on Phase 2 — establishes the full provisioning pipeline; all other phases can start after Phase 2 but US1 must complete before Phase 4 (US2 reuses the provisioning agent)
- **Phase 4 (US2 Bucket)**: Depends on Phase 2 and Phase 3 agent/MCP foundations
- **Phase 5 (US3 Enquiry)**: Depends on Phase 2 only — fully independent of provisioning
- **Phase 6 (US4 FAQ)**: Depends on Phase 2 only — fully independent of provisioning and enquiry
- **Phase 7 (VPC)**: Depends on Phase 3 (reuses provisioning agent patterns)
- **Phase 8 (Polish)**: Depends on Phases 3–6 all complete

### User Story Dependencies

- **US1 (VM)**: Foundational only — no story dependencies
- **US2 (Bucket)**: Foundational + US1 agent/MCP server established (T036–T040, T045–T048)
- **US3 (Enquiry)**: Foundational only — fully independent
- **US4 (FAQ)**: Foundational only — fully independent

### Within Each Phase

1. Contract tests → MCP servers → Skills → Agents → DAG/Web → Integration tests
2. Models (Pydantic contracts) before services (agents/skills)
3. MCP servers before skills (skills call MCP servers)
4. Skills before agents (agents orchestrate skills)

### Parallel Opportunities

- All Phase 1 tasks marked [P] run in parallel
- All Phase 2 schema tasks (T013–T015) sequential; contract models (T016–T025) all parallel; shared infra (T026–T032) all parallel
- Within Phase 3: T033–T035 (contract tests), T036–T040 (MCP servers), T041 (classification skill) all parallel; T042–T044 (compute skills) parallel among themselves
- US3 (Phase 5) and US4 (Phase 6) can be worked in parallel with US2 (Phase 4) by different developers

---

## Parallel Example: Phase 3 MCP Servers

```
Launch together (no interdependencies, different files):
- T036: mcp_servers/postgres/server.py
- T037: mcp_servers/pubsub/server.py
- T038: mcp_servers/gcp_resource/server.py (VM subset)
- T039: mcp_servers/backstage/server.py
- T040: mcp_servers/gmail/server.py
- T041: skills/intent_classification/classifier.py
```

---

## Implementation Strategy

### MVP: User Story 1 Only

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational) — CRITICAL
3. Complete Phase 3 (US1: VM Provisioning) — full pipeline: web UI → confirmation → Airflow DAG → GCP → SSE
4. **STOP and VALIDATE**: Submit "Create a VM with 4 CPUs in us-central1" end-to-end
5. Demo to stakeholders

### Incremental Delivery

1. MVP (US1) → validated → demo
2. Add US2 (bucket) → test independently → demo
3. Add US3 (enquiry) → test independently → demo
4. Add US4 (FAQ) → test independently → demo
5. Each story adds value without modifying previous story behaviour

### Parallel Team Strategy

After Phase 2 completes:
- **Developer A**: US1 (VM provisioning) — Phase 3
- **Developer B**: US3 (Enquiry) — Phase 5 (independent of US1)
- **Developer C**: US4 (FAQ) — Phase 6 (independent of US1)
- Once US1 is done: Developer A moves to US2 (Bucket) — Phase 4

---

## Notes

- [P] = different files, no dependency on any incomplete task in the same phase
- [USn] = maps task to user story for independent delivery traceability
- `awaiting_confirmation` and `queued` are the canonical ProvisioningJob states — never use `pending`
- Channel enum: `web` for browser requests, `email` for Gmail channel — never `chatbot`
- Email channel: low-confidence requests are rejected, not clarified (see `CONTEXT.md`)
- `rollback_resources` starts empty on job creation — appended after each successful GCP create (ADR 0006)
- Backstage registration failure triggers full rollback (ADR 0005) — test this explicitly in T067
- Commit after each checkpoint or logical task group
- Run `evaluations/intent_classification/evaluate.py` before any release — must score ≥ 90%
