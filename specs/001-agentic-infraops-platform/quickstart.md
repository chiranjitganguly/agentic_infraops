# Quickstart: Local Development

**Stack**: Docker Compose | **Date**: 2026-05-10

The full InfraOps platform runs locally via Docker Compose. No cloud deployment is required for development or testing.

## Prerequisites

- Docker Desktop 4.x+ (or Docker Engine + Compose plugin)
- Python 3.11+ (for running tests and scripts outside Docker)
- GCP project with a service account JSON key (for GCP API calls — can be stubbed for unit tests)
- Gmail API credentials (OAuth2 client JSON — for email polling)
- Google API key or OpenAI API key (for LiteLLM embeddings)

## 1. Clone and Configure

```bash
git clone <repo>
cd agentic_infraops
cp .env.example .env
```

Edit `.env`:
```bash
# GCP
GCP_PROJECT_ID=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa-key.json

# LiteLLM
LITELLM_MASTER_KEY=sk-local-dev-key
GOOGLE_API_KEY=your-google-api-key          # for Gemini via LiteLLM
OPENAI_API_KEY=your-openai-api-key          # for embeddings (optional)

# Gmail
GMAIL_CREDENTIALS_PATH=/run/secrets/gmail-credentials.json
GMAIL_INBOX_ADDRESS=infraops@yourorg.com

# PostgreSQL
POSTGRES_PASSWORD=infraops_local_dev

# Airflow
AIRFLOW__CORE__FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

## 2. Start the Stack

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

This starts:

| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5432 | PostgreSQL 15 — application state |
| `qdrant` | 6333, 6334 | Qdrant — FAQ knowledge base |
| `pubsub-emulator` | 8085 | GCP PubSub emulator |
| `litellm` | 4000 | LiteLLM proxy gateway |
| `airflow-webserver` | 8080 | Airflow UI |
| `airflow-scheduler` | — | Airflow scheduler |
| `orchestrator-agent` | 8001 | Orchestrator A2A agent |
| `provisioning-agent` | 8002 | Provisioning A2A agent |
| `enquiry-agent` | 8003 | Enquiry A2A agent |
| `faq-agent` | 8004 | FAQ A2A agent |
| `web-backend` | 8000 | FastAPI web UI backend |
| `web-frontend` | 3000 | Web UI |
| `gmail-poller` | — | Gmail inbox polling service |
| `prometheus` | 9090 | Metrics |
| `grafana` | 3000 | Dashboards |

## 3. Initialize the Database

```bash
docker compose -f docker/docker-compose.yml exec postgres psql -U infraops -d infraops -f /docker-entrypoint-initdb.d/schema.sql
```

Or run the migration script:
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/infraops python infrastructure/scripts/migrate.py
```

## 4. Seed the Knowledge Base

```bash
python infrastructure/scripts/seed_knowledge_base.py \
  --knowledge-dir docs/knowledge/ \
  --qdrant-url http://localhost:6333
```

This chunks and indexes all Markdown files in `docs/knowledge/` into Qdrant.

## 5. Create a Test User

```bash
python infrastructure/scripts/create_user.py \
  --user-id dev@yourorg.com \
  --role developer
```

The script prints the API key (shown once — copy it now):
```
API key: infraops_<base64url>
Expires: 2026-08-08T00:00:00Z
```

## 6. Test the End-to-End VM Provisioning Flow

```bash
# Submit a provisioning request
curl -X POST http://localhost:8000/api/v1/requests \
  -H "Authorization: Bearer infraops_<your_key>" \
  -H "Content-Type: application/json" \
  -d '{"raw_input": "Create a VM with 4 CPUs in us-central1", "channel": "chatbot"}'
```

Response includes `job_id` and `confirmation_summary`. Confirm:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/<job_id>/confirm \
  -H "X-API-Key: infraops_<your_key>"
```

Stream live status:

```bash
curl -H "X-API-Key: infraops_<your_key>" \
     -H "Accept: text/event-stream" \
     "http://localhost:8000/api/v1/jobs/<job_id>/stream"
```

## 7. Test the FAQ Flow

```bash
curl -X POST http://localhost:8000/api/v1/requests \
  -H "Authorization: Bearer infraops_<your_key>" \
  -H "Content-Type: application/json" \
  -d '{"raw_input": "What is the best practice for VPC design on GCP?", "channel": "chatbot"}'
```

## 8. Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Contract tests
pytest tests/contract/ -v

# Integration tests (requires full Docker Compose stack)
pytest tests/integration/ -v --env local

# Workflow tests (Airflow DAG unit tests)
pytest tests/workflow/ -v
```

## 9. View Observability

- **Airflow UI**: http://localhost:8080 (admin / admin)
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin / admin)
- **Qdrant UI**: http://localhost:6333/dashboard
- **LiteLLM UI**: http://localhost:4000/ui

## 10. Useful Commands

```bash
# View logs for a specific service
docker compose -f docker/docker-compose.yml --env-file .env logs -f orchestrator-agent

# Restart a single service after code change
docker compose -f docker/docker-compose.yml --env-file .env up -d --no-deps --build orchestrator-agent

# Stop the stack
docker compose -f docker/docker-compose.yml --env-file .env down

# Stop and remove all volumes (reset state)
docker compose -f docker/docker-compose.yml --env-file .env down -v

# Run a one-off command in a container
docker compose exec web-backend python -m pytest tests/unit/ -v
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| PubSub messages not picked up by Airflow | Verify `PUBSUB_EMULATOR_HOST=pubsub-emulator:8085` is set in Airflow containers |
| Qdrant search returns no results | Check knowledge base was seeded: `curl http://localhost:6333/collections/infraops_knowledge_base` |
| LiteLLM returns 401 | Verify `LITELLM_MASTER_KEY` matches in `.env` and agent config |
| SSE stream closes immediately | Check PostgreSQL LISTEN/NOTIFY trigger is installed: `\df notify_job_status_change` in psql |
| Gmail polling not receiving messages | Verify `GMAIL_CREDENTIALS_PATH` is mounted and OAuth token is valid; check `docker compose logs gmail-poller` |
