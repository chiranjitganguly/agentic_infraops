# Implementation Plan: Agentic InfraOps Self-Service Platform (Phase 1)

**Branch**: `001-agentic-infraops-platform` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-agentic-infraops-platform/spec.md`

## Summary

Build a multi-agent, event-driven infrastructure self-service platform on GCP supporting VM provisioning, storage bucket provisioning, resource status enquiry, and FAQ/best-practice guidance. The platform is delivered as a locally runnable Docker Compose stack, with Google Agent Development Kit agents communicating via native A2A protocol, Apache Airflow executing provisioning workflows triggered by Cloud PubSub, and a custom web UI with SSE-based real-time updates. All external integrations are accessed through MCP servers. LiteLLM provides the unified LLM access layer.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Google Agent Development Kit (agent framework), Apache Airflow 2.8+ (workflow engine), LiteLLM (LLM gateway), Pydantic v2 (schema validation), FastAPI (web UI backend + SSE), asyncpg (async PostgreSQL), Qdrant (local vector DB), google-api-python-client (Gmail API), google-cloud-pubsub (PubSub + emulator), apache-airflow-providers-google (PubSub sensors), mcp (MCP server library), pytest + pytest-asyncio (testing)
**Storage**: PostgreSQL 15 in Docker (ProvisioningJob state, audit log, user roles, API keys); Qdrant in Docker (FAQ knowledge base — hybrid BM25 + dense vector)
**Testing**: pytest with pytest-asyncio; contract tests via pydantic validation; Airflow DAG unit tests via `pytest-airflow`
**Target Platform**: Docker Compose (local development); GCP + Kubernetes (future cloud deployment)
**Project Type**: Multi-service monorepo platform (agents + skills + MCP servers + workflows + web UI)
**Performance Goals**: Provisioning end-to-end ≤10 min; status enquiry response ≤30 s; FAQ response ≤60 s; 50 concurrent requests without degradation
**Constraints**: Stateless agents; horizontal scaling; 99.5% monthly uptime target; API key auth (≤90 day expiry); email requests under developer-role guardrails only; 20-minute confirmation timeout; developer daily provisioning cap of 10 resources
**Scale/Scope**: Phase 1 — developer + platform engineer users; VM + bucket + basic VPC provisioning; all GCP resources in project queryable

## Constitution Check

*GATE: Must pass before Phase 0 research.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Agent-First Design | ✅ Pass | All operations via agents; skills preferred over duplicated logic |
| II. Infrastructure-as-Code | ✅ Pass | All infra definitions in source control; IaC via Terraform in `infrastructure/` |
| III. Observability-First | ✅ Pass | Structured logging, Prometheus metrics, distributed tracing, audit events on all components |
| IV. Safety & Guardrails | ⚠️ Gap | **Dry-run capability** and **circuit breakers for GCP APIs** required by constitution but not in spec — added as plan-level requirements below |
| V. Idempotency & Resilience | ✅ Pass | Idempotency key = `(resource_type, name, region)`; exponential backoff with jitter; full rollback on partial failure |
| VI. Contract-First | ✅ Pass | Schemas, event contracts, MCP interfaces, and A2A agent contracts defined before implementation |
| VII. Agent Governance | ✅ Pass | Each agent has explicit contract; business logic in skills, not DAGs; DAGs are thin orchestration wrappers |
| VIII. Knowledge & FAQ | ✅ Pass | Hybrid retrieval (BM25 + vector); Qdrant; source attribution enforced |
| IX. Cloud Extensibility | ✅ Pass | GCP logic isolated behind MCP server adapters and skills |
| X. Approved Technology | ✅ Pass | Python, Google ADK, Airflow, Backstage, PubSub, GCP, LiteLLM, MCP, pytest, Docker — all approved |
| XI. Skills-First | ✅ Pass | Six shared skill packages defined; agents orchestrate skills |
| XII. LLM Access | ✅ Pass | All LLM access via LiteLLM gateway; direct provider SDK prohibited |
| XIII. Python Engineering | ✅ Pass | Type hints, Pydantic, Ruff, Black, async-first patterns |
| XIV. Testing & Evaluation | ✅ Pass | pytest, integration tests, contract tests, evaluation datasets, hallucination checks |
| XV. Local Development | ✅ Pass | Full Docker Compose stack; PubSub emulator; local Qdrant; local LiteLLM |

### Plan-Level Requirements (Constitution IV Gaps)

- **PLR-001**: All provisioning skills MUST support a `dry_run: bool` parameter. When `dry_run=True`, the skill validates parameters and returns what would be created without calling GCP APIs.
- **PLR-002**: All GCP API calls MUST be wrapped with a circuit breaker (open after 5 consecutive failures, half-open after 60 seconds). Circuit breaker state MUST be observable via metrics.

## Project Structure

### Documentation (this feature)

```text
specs/001-agentic-infraops-platform/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions and state machines
├── quickstart.md        # Phase 1: local development guide
├── contracts/           # Phase 1: interface contracts
│   ├── pubsub-events.md
│   ├── a2a-agents.md
│   ├── mcp-servers.md
│   └── web-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
agentic_infraops/
├── agents/
│   ├── orchestrator/          # Intent classification, routing, confirmation flow
│   ├── provisioning/          # Provisioning task execution, PubSub publishing
│   ├── enquiry/               # GCP resource status retrieval
│   └── faq/                   # Hybrid retrieval + answer generation
├── skills/
│   ├── gcp_compute/           # VM provisioning + dry-run + rollback
│   ├── gcp_storage/           # Bucket provisioning + dry-run + rollback
│   ├── gcp_network/           # VPC + subnet creation
│   ├── status_query/          # GCP resource status retrieval (all resource types)
│   ├── document_retrieval/    # Hybrid BM25 + vector search against Qdrant
│   └── intent_classification/ # NL → intent + parameter extraction via LiteLLM
├── mcp_servers/
│   ├── gcp_resource/          # Wraps Compute + Storage + Network GCP APIs
│   ├── knowledge_base/        # Wraps Qdrant hybrid search
│   ├── postgres/              # Wraps PostgreSQL (jobs, audit, users, API keys)
│   ├── pubsub/                # Wraps PubSub publish operations
│   ├── airflow/               # Wraps Airflow REST API (DAG status queries)
│   ├── backstage/             # Wraps Backstage catalog API
│   └── gmail/                 # Wraps Gmail API (poll, send, thread correlation)
├── workflows/
│   ├── dags/
│   │   ├── provision_vm_dag.py      # VM provisioning DAG
│   │   └── provision_bucket_dag.py  # Bucket provisioning DAG
│   └── sensors/                     # PubSub pull sensors
├── contracts/                 # Shared Pydantic models (symlinked from specs/)
│   ├── schemas/
│   ├── events/
│   └── agents/
├── web/
│   ├── backend/               # FastAPI: request submission, SSE, job status, auth
│   └── frontend/              # Web UI (lightweight HTML/JS or React)
├── evaluations/
│   ├── datasets/              # Versioned evaluation datasets
│   ├── intent_classification/ # Intent accuracy evaluation
│   └── faq/                   # RAG grounding + hallucination checks
├── infrastructure/
│   ├── terraform/             # GCP IaC definitions
│   └── scripts/               # Setup and migration scripts
├── docker/
│   ├── docker-compose.yml     # Full local stack
│   └── services/              # Per-service Dockerfiles
├── observability/
│   ├── prometheus/            # Metrics config
│   └── grafana/               # Dashboards
└── docs/
    ├── architecture/
    ├── runbooks/
    └── onboarding/

tests/
├── unit/
├── integration/
├── contract/
└── workflow/
```

**Structure Decision**: Monorepo with domain-separated top-level directories. Agents, skills, and MCP servers are independent Python packages within the monorepo, each with their own `pyproject.toml`. Shared contracts are defined once in `contracts/` and imported by all packages.

## Implementation Phases

### Phase 1: Foundation Setup
- Monorepo scaffolding with Python package structure
- Docker Compose stack: PostgreSQL, Qdrant, LiteLLM gateway, Airflow, PubSub emulator, Prometheus, Grafana
- Shared config module (environment-driven, no secrets in code)
- Structured logging framework with correlation_id + request_id propagation
- Base Pydantic models and schema validation pipeline
- CI/CD scaffolding (lint, test, schema validation gates)

### Phase 2: Contract & Schema Layer
- All Pydantic request/response models
- PubSub event contracts (versioned, immutable)
- A2A agent contracts (agent cards + task schemas)
- MCP server tool definitions
- Web API OpenAPI spec
- Schema validation test suite

### Phase 3: MCP Servers
- `gcp-resource-mcp`: GCP Compute + Storage + Network API wrapper
- `knowledge-base-mcp`: Qdrant hybrid search wrapper
- `postgres-mcp`: PostgreSQL CRUD + LISTEN/NOTIFY wrapper
- `pubsub-mcp`: PubSub publish wrapper
- `airflow-mcp`: Airflow REST API wrapper
- `backstage-mcp`: Backstage catalog API wrapper
- `gmail-mcp`: Gmail API polling + send wrapper

### Phase 4: Skills Implementation
- `intent_classification` skill: NL → (intent, confidence, normalized_params) via LiteLLM
- `gcp_compute` skill: create VM, dry-run, rollback (delete VM)
- `gcp_storage` skill: create bucket, dry-run, rollback (delete bucket)
- `gcp_network` skill: create VPC network + subnet
- `status_query` skill: get resource status from GCP (VM, bucket, VPC)
- `document_retrieval` skill: BM25 pre-filter + vector rerank against Qdrant

### Phase 5: Agents
- Orchestrator agent: intent routing, confirmation flow, rate limit enforcement, guardrail checks, clarification loop
- Provisioning agent: job creation, idempotency check, PubSub publish, confirmation summary
- Enquiry agent: resource status retrieval, RBAC-scoped results
- FAQ agent: retrieval-augmented answer generation with source citation

### Phase 6: Airflow Workflows
- `provision_vm_dag`: PubSubPullSensor → validate → dry-run → provision → update job state → publish status event → register in Backstage
- `provision_bucket_dag`: same structure, bucket-specific tasks
- Retry logic: exponential backoff with jitter, max 3 retries
- Rollback task group: triggered on exhausted retries

### Phase 7: Web UI & Email Poller
- FastAPI backend: API key auth middleware, request submission, job status, SSE endpoint, confirmation endpoint
- PostgreSQL LISTEN/NOTIFY → SSE push pipeline
- Gmail poller: 30s interval, unread message processing, thread ID correlation for confirmations
- Web frontend: chat interface, job status view, SSE subscription

### Phase 8: Evaluation & Testing
- pytest suite: unit, integration, contract, workflow tests
- Intent classification evaluation dataset (≥100 labelled examples)
- FAQ grounding evaluation (≥50 Q&A pairs with source verification)
- Hallucination detection checks
- End-to-end flow tests for all three primary flows

### Phase 9: Backstage & Documentation
- Backstage catalog entries for all agents, skills, and MCP servers
- Operational runbooks
- Architecture documentation
- Developer onboarding guide

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Orchestration complexity — Google Agent Development Kit A2A protocol learning curve | High | High | Build tracer-bullet A2A flow (orchestrator → provisioning agent) in Phase 5 before full implementation |
| Schema evolution — PubSub message format changes | Medium | High | Version all events from day one; additive-only evolution policy enforced in CI |
| PubSub message reliability — at-least-once delivery causing duplicate jobs | Medium | High | Idempotency key enforced at PostgreSQL level before job creation |
| Agent hallucination — LLM misclassifies intent or generates invalid parameters | High | Medium | Evaluation dataset + classification accuracy gate (≥90% SC-002); dry-run validation before execution |
| Workflow retry inconsistency — Airflow retries and agent retries conflicting | Medium | High | Airflow handles all retries; agent publishes once and awaits status events |
| GCP API rate limits — burst provisioning requests hitting quota | Low | Medium | Circuit breaker (PLR-002) + daily rate limit (FR-021) + exponential backoff (Q14) |
| Gmail polling reliability — auto-replies triggering unintended confirmations | Medium | Medium | Reply filter: only process emails in the same thread as a sent confirmation; body must contain "confirm" or "yes" |
