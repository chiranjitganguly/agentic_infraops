# Research: Agentic InfraOps Self-Service Platform (Phase 1)

**Branch**: `001-agentic-infraops-platform` | **Date**: 2026-05-10

## 1. Local Vector Database — Qdrant

**Decision**: Qdrant (self-hosted in Docker)

**Rationale**: Qdrant is the only open-source vector database with native hybrid search support — combining sparse vectors (BM25 via SPLADE) and dense vectors in a single query without client-side orchestration. ChromaDB requires external BM25 libraries and client-side score fusion. Weaviate supports hybrid search but has higher operational complexity. Qdrant's Docker image is lightweight and production-grade.

**Hybrid search pattern**:
```
Query → BM25 sparse embedding + dense embedding → Qdrant hybrid query (RRF fusion) → top-k chunks → LiteLLM synthesis
```

**Configuration**:
- Docker image: `qdrant/qdrant:latest`
- Port: 6333 (HTTP), 6334 (gRPC)
- Collection: `infraops_knowledge_base`
- Vector size: 1536 (OpenAI text-embedding-3-small) or 768 (local embedding model via LiteLLM)
- Sparse vectors: Qdrant built-in BM25 (FastEmbed)

**Alternatives considered**: ChromaDB (no native hybrid search), Weaviate (more complex ops), pgvector (no hybrid search, already using PostgreSQL for relational data)

---

## 2. Gmail API Polling

**Decision**: Gmail API with `history.list()` incremental sync, 30-second polling interval

**Rationale**: Gmail API is the correct integration for a GCP-first stack using Google Workspace identities. The `history.list()` API is more efficient than `messages.list()` — it returns only changes since the last `historyId`, avoiding re-processing already-seen messages.

**Pattern**:
1. On startup: `messages.list(userId='me', labelIds=['INBOX'], q='is:unread to:infraops@org.com')` to process backlog
2. Store `historyId` from the last processed message
3. Every 30s: `history.list(userId='me', startHistoryId=<last_id>)` for incremental changes
4. For each new message: extract sender, subject, body; strip quoted content (detect `>` or `On ... wrote:` patterns)
5. Mark as read after processing: `messages.modify(userId='me', id=<msg_id>, removeLabelIds=['UNREAD'])`

**Confirmation reply detection**:
- Only process replies in the same `threadId` as a sent confirmation email
- Body must contain "confirm", "yes", "approve" (case-insensitive, after stripping quoted content)
- Auto-reply detection: skip if `X-Autoreply`, `Auto-Submitted`, or `X-Auto-Response-Suppress` headers present

**Quota**: Gmail API allows 250 quota units/second per user. `history.list` costs 1 unit. 30s polling = ~2 units/minute — well within quota.

**Alternatives considered**: IMAP polling (simpler but no incremental sync, connection management), SendGrid inbound parse (third-party dependency), Cloud Run push subscription (more complex setup)

---

## 3. Google Cloud PubSub Emulator (Local)

**Decision**: `gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators` Docker image

**Pattern**:
```bash
gcloud beta emulators pubsub start --host-port=0.0.0.0:8085
export PUBSUB_EMULATOR_HOST=localhost:8085
```

**Topic naming convention** (see contracts/pubsub-events.md for full schema):
- `infraops.provisioning.requests` — agent → Airflow trigger
- `infraops.provisioning.status` — Airflow → notification service
- `infraops.audit.events` — all agents → audit sink

**Local setup**: Docker Compose service `pubsub-emulator` starts the emulator and exposes port 8085. All services set `PUBSUB_EMULATOR_HOST=pubsub-emulator:8085`. The `pubsub-mcp` MCP server auto-creates topics and subscriptions on startup if they do not exist.

---

## 4. Google Agent Development Kit A2A Protocol

**Decision**: Google Agent Development Kit native A2A protocol with agent cards and task lifecycle API

**Pattern**:
- Each agent is an HTTP service exposing a `/.well-known/agent.json` agent card endpoint
- Orchestrator maintains an in-memory agent registry (agent cards loaded at startup)
- Task lifecycle: `submitted → working → completed / failed`
- Orchestrator POSTs a Task object to the target agent's `/tasks` endpoint
- Agent responds with task updates (synchronously or via SSE streaming for long tasks)

**Agent card structure**:
```json
{
  "name": "provisioning-agent",
  "description": "Executes infrastructure provisioning tasks on GCP",
  "version": "1.0.0",
  "capabilities": ["provision_vm", "provision_bucket", "provision_vpc"],
  "inputSchema": "<reference to contracts/agents/provisioning-agent-input.json>",
  "outputSchema": "<reference to contracts/agents/provisioning-agent-output.json>"
}
```

**Correlation**: Every task carries `correlation_id` (UUID, generated at request ingestion) and `request_id` (UUID, per-task). Both are propagated across all A2A calls, PubSub messages, and log entries.

---

## 5. LiteLLM Gateway

**Decision**: LiteLLM Proxy (Docker), configured via `litellm_config.yaml`

**Rationale**: Provides a single OpenAI-compatible endpoint for all LLM calls from agents and business_logic modules. Supports model routing, caching, rate limiting, spend tracking, and provider fallback. Eliminates direct provider SDK imports in agent code (Constitution XII).

**Configuration highlights**:
```yaml
model_list:
  - model_name: default
    litellm_params:
      model: gemini/gemini-1.5-pro
      api_key: os.environ/GOOGLE_API_KEY
  - model_name: embedding
    litellm_params:
      model: text-embedding-3-small
      api_key: os.environ/OPENAI_API_KEY

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/LITELLM_DB_URL

litellm_settings:
  request_timeout: 30
  num_retries: 3
  fallbacks: [{default: [gemini/gemini-1.5-flash]}]
```

**Metrics**: LiteLLM exposes Prometheus metrics at `/metrics` — token usage, latency, error rates per model.

---

## 6. PostgreSQL SSE via LISTEN/NOTIFY

**Decision**: `asyncpg` with `LISTEN/NOTIFY` for SSE push

**Pattern**:
```python
# On job state change (Airflow DAG or agent updates job status):
NOTIFY infraops_job_status, '{"job_id": "...", "status": "succeeded", ...}';

# SSE endpoint (FastAPI):
async def job_stream(job_id: str, conn: asyncpg.Connection):
    queue = asyncio.Queue()
    await conn.add_listener('infraops_job_status', lambda *args: queue.put_nowait(args))
    async def event_generator():
        while True:
            payload = await queue.get()
            data = json.loads(payload[3])
            if data['job_id'] == job_id:
                yield f"data: {json.dumps(data)}\n\n"
    return EventSourceResponse(event_generator())
```

**Fallback**: If the SSE connection drops, the client polls `GET /api/v1/jobs/{job_id}` as fallback. Job state is always authoritative in PostgreSQL.

---

## 7. MCP Servers

**Decision**: Python `mcp` library (Anthropic MCP SDK) for all MCP server implementations

**Rationale**: The `mcp` library provides the standardised server implementation with tool registration, schema validation, and JSON-RPC transport. Each MCP server is a lightweight Python service that wraps one external system.

**Server startup pattern** (each MCP server):
```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("gcp-resource-mcp")

@server.tool()
async def get_vm_status(project_id: str, zone: str, instance_name: str) -> dict:
    ...

async def main():
    async with stdio_server() as streams:
        await server.run(*streams)
```

**Transport**: stdio (agents invoke MCP servers as subprocesses). For Docker Compose deployment, each MCP server runs as a sidecar container with stdio bridged via a Unix socket.

---

## 8. Airflow PubSub Integration

**Decision**: `apache-airflow-providers-google` with `PubSubPullSensor`

**Pattern** (per DAG):
```python
from airflow.providers.google.cloud.sensors.pubsub import PubSubPullSensor
from airflow.providers.google.cloud.operators.pubsub import PubSubPullOperator

pull_message = PubSubPullSensor(
    task_id='wait_for_provisioning_request',
    project_id=GCP_PROJECT_ID,
    subscription='infraops-provisioning-requests-sub',
    max_messages=1,
    poke_interval=10,
    timeout=300,
)
```

**DAG trigger**: Airflow is configured with `AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=30`. DAGs are triggered by the PubSub sensor — no external DAG trigger API call needed. This avoids the Airflow REST API dependency for the provisioning trigger path.

---

## 9. API Key Authentication

**Decision**: FastAPI middleware with PostgreSQL-backed API key store, bcrypt hashed, 90-day expiry

**Key lifecycle**:
- Keys are 32-byte random tokens, base64url encoded
- Stored as bcrypt hash in `user_roles.api_key_hash`
- `api_key_expires_at` = issued_at + 90 days
- `api_key_last_used` updated on each authenticated request (async, non-blocking)
- Keys rotate via `POST /api/v1/auth/rotate-key` (requires current valid key)

**Request flow**:
```
Request → X-API-Key header → FastAPI middleware → bcrypt verify against DB → attach UserRole → proceed
```

**Security notes** (flagged from grill-me session):
- Keys transmitted only over TLS
- Keys never logged (redacted in structured logs)
- Expired keys return 401 with `WWW-Authenticate: ApiKey` and renewal instructions
- Brute-force protection: 5 failed attempts per IP per minute → 429

---

## 10. Circuit Breaker Pattern (PLR-002)

**Decision**: `circuitbreaker` Python library wrapping all GCP API calls in business_logic

**Configuration**:
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60, expected_exception=GCPAPIError)
async def create_vm(project_id: str, zone: str, config: VMConfig) -> str:
    ...
```

**Observability**: Circuit state (closed/open/half-open) exposed as a Prometheus gauge per skill per GCP API type. Alert when any circuit opens.
