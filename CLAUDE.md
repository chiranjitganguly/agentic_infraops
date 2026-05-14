# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

For additional context about technologies to be used, project structure, shell commands, and other important information, read the current plan at specs/001-agentic-infraops-platform/plan.md

## Project Overview

Multi-agent, event-driven GCP infrastructure self-service platform. Developers submit natural-language requests (via chatbot or email) to provision VMs/buckets/VPCs, query resource status, or get FAQ answers. The full stack runs locally via Docker Compose.

**Key technologies**: Google Agent Development Kit (agents), Apache Airflow 2.9 with CeleryExecutor (workflows), LiteLLM (LLM gateway — all LLM calls must go through it, direct provider SDK is prohibited), FastAPI (web backend + SSE), PostgreSQL 15, Qdrant (vector DB), GCP PubSub emulator, MCP servers (7 total).

## Commands

### Running Tests

```bash
# Unit tests (no external services required)
pytest tests/unit -m "not integration" --tb=short

# Contract tests (Pydantic schema validation)
pytest tests/contract -m "contract" --tb=short

# Integration tests (requires full Docker Compose stack)
pytest tests/integration -v --env local

# Workflow tests (Airflow DAG unit tests)
pytest tests/workflow -v

# Single test
pytest tests/unit/agents/test_orchestrator.py::TestOrchestrator::test_route_provision -v
```

### Lint, Format, Type Check

```bash
ruff check agentic_infraops infrastructure tests   # lint
black --check agentic_infraops infrastructure tests # format check
black agentic_infraops infrastructure tests         # format fix
mypy agentic_infraops --ignore-missing-imports      # type check
```

### Local Stack

```bash
# Start everything
docker compose -f docker/docker-compose.yml --env-file .env up -d

# View logs for a service
docker compose -f docker/docker-compose.yml --env-file .env logs -f orchestrator-agent

# Rebuild and restart a single service after code change
docker compose -f docker/docker-compose.yml --env-file .env up -d --no-deps --build orchestrator-agent

# Stop and reset all state
docker compose -f docker/docker-compose.yml --env-file .env down -v
```

### Setup Scripts

```bash
# Run DB migrations
python infrastructure/scripts/migrate.py --env local

# Seed Qdrant knowledge base from docs/knowledge/
python infrastructure/scripts/seed_knowledge_base.py --docs-dir docs/knowledge/ --qdrant-url http://localhost:6333

# Create a test user (prints API key once)
python infrastructure/scripts/create_user.py --user-id dev@yourorg.com --role developer
```

## Architecture

### Request Flow

Email/chatbot → `web-backend` (FastAPI, port 8000) → `orchestrator-agent` (port 8001) → intent classification → guardrail check → route to sub-agent:
- **Provision**: `provisioning-agent` (port 8002) → publishes PubSub event → Airflow DAG picks up via PubSubPullSensor → provisions GCP resource → publishes status event → `notification-service` → Gmail notification + PostgreSQL LISTEN/NOTIFY → SSE push to web UI
- **Enquiry**: `enquiry-agent` (port 8003) → `mcp-gcp-resource` → GCP API → response
- **FAQ**: `faq-agent` (port 8004) → `mcp-knowledge-base` → Qdrant hybrid search → LiteLLM answer generation

### Agent Design Pattern

Agents are stateless. Business logic lives in **skills** (`agentic_infraops/skills/` and `skills/`), not in agents or DAGs. DAGs are thin orchestration wrappers. Agents communicate via Google ADK native A2A protocol. All agents implement `OrchestratorInput`/`OrchestratorOutput` style dataclass contracts.

### Skills (Business Logic Layer)

`skills/gcp_compute/` — VM provisioning with `dry_run: bool` parameter (required by PLR-001: all provisioning skills must support dry-run). All GCP API calls wrapped with circuit breaker (opens after 5 consecutive failures, PLR-002).

### MCP Servers

Seven MCP servers, each in `agentic_infraops/mcp_servers/<name>/` with a corresponding Dockerfile in `docker/services/mcp_<name>/`. They are: `gcp_resource`, `knowledge_base`, `postgres`, `pubsub`, `airflow`, `backstage`, `gmail`.

### Contracts

Pydantic v2 models define all inter-component interfaces. Located in `contracts/` (root) and `agentic_infraops/contracts/`. PubSub event schemas are versioned and additive-only (breaking changes blocked in CI via schema validation gate). Contract tests in `tests/contract/` validate all schemas import cleanly.

### Key Architectural Decisions (see `docs/adr/`)

- **ADR-0001**: Skills are the business logic layer — agents and DAGs must not contain provisioning logic directly
- **ADR-0002**: Single resource per request — no bulk operations
- **ADR-0003**: Airflow DAG owns job state — agents publish once and await status events
- **ADR-0004**: Provisioning job state machine — states: `pending → confirmed → queued → in_progress → completed | failed | rolled_back`
- **ADR-0005**: Backstage registration is a hard requirement — every provisioned resource must be registered
- **ADR-0006**: Rollback resources are appended after create, not replace

### Configuration

All configuration via environment variables. Copy `.env.example` to `.env`. Required secrets: `GCP_SA_KEY_PATH` (GCP service account JSON), `GMAIL_CREDENTIALS_PATH` (OAuth2 JSON), API keys for LiteLLM providers.

Developer guardrails enforced at orchestrator level: `ALLOWED_REGIONS`, `ALLOWED_MACHINE_TYPES`, `ALLOWED_STORAGE_CLASSES`, `DEVELOPER_DAILY_LIMIT=10` (provisioning cap per user per day).

## Testing Strategy

- **Unit tests** (`tests/unit/`): no external services; use `Protocol`-based dependency injection to mock all clients
- **Contract tests** (`tests/contract/`): Pydantic schema import validation only
- **Integration tests** (`tests/integration/`): require full Docker Compose stack; marked `@pytest.mark.integration`
- **Workflow tests** (`tests/workflow/`): Airflow DAG unit tests via `pytest-airflow`

pytest markers: `unit`, `integration`, `contract`, `workflow`, `slow`

## Service Ports (local)

| Service | Port |
|---------|------|
| web-backend | 8000 |
| orchestrator-agent | 8001 |
| provisioning-agent | 8002 |
| enquiry-agent | 8003 |
| faq-agent | 8004 |
| airflow-webserver | 8080 |
| pubsub-emulator | 8085 |
| prometheus | 9090 |
| litellm | 4000 |
| qdrant | 6333 |
| grafana | 3000 |
| postgres | 5432 |
