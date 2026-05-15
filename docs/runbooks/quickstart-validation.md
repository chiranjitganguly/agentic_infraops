# Runbook: Quickstart Validation

**Task:** T100 — Validate `quickstart.md` end-to-end  
**Validated against:** Docker Compose stack, CLAUDE.md, service Dockerfiles  
**Date:** 2026-05-15

---

## Summary of Findings

Validated `specs/001-agentic-infraops-platform/quickstart.md` against the actual codebase configuration. The following discrepancies were found and fixed directly in `quickstart.md`.

---

## Discrepancies Found and Fixed

### 1. Agent ports in service table (wrong)

**Quickstart listed:**
- `orchestrator-agent` → 8100
- `provisioning-agent` → 8101
- `enquiry-agent` → 8102
- `faq-agent` → 8103

**Correct ports (from `CLAUDE.md` and agent `__main__` blocks):**
- `orchestrator-agent` → 8001
- `provisioning-agent` → 8002
- `enquiry-agent` → 8003
- `faq-agent` → 8004

**Fix:** Updated service port table in quickstart step 2.

### 2. `docker compose` command missing file flag

**Quickstart used:** `docker compose up -d`  
**CLAUDE.md canonical form:** `docker compose -f docker/docker-compose.yml --env-file .env up -d`

**Fix:** All `docker compose` commands in quickstart updated to include `-f docker/docker-compose.yml --env-file .env`.

### 3. `seed_knowledge_base.py` flag mismatch

**Quickstart used:** `--docs-dir docs/knowledge/`  
**CLAUDE.md canonical form:** `--knowledge-dir docs/knowledge/`

**Fix:** Updated step 4 in quickstart.

### 4. `migrate.py` flag mismatch

**Quickstart used:** `python infrastructure/scripts/migrate.py --env local`  
**CLAUDE.md canonical form:** `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/infraops python infrastructure/scripts/migrate.py`

**Fix:** Updated step 3 in quickstart.

### 5. Curl command uses wrong auth header

**Quickstart used:** `X-API-Key: infraops_<your_key>`  
**web/backend auth middleware:** expects `Authorization: Bearer <key>`

**Fix:** Updated all curl examples to use `Authorization: Bearer infraops_<your_key>`.

### 6. Grafana port

**Quickstart listed:** `grafana` → 3001  
**CLAUDE.md:** `grafana` → 3000

**Fix:** Updated service port table and observability section.

---

## Validation Checklist

The following steps were traced through the codebase (not run against a live stack, as this is a code-level validation):

- [x] Step 1 — Clone and configure: `.env.example` exists, all documented variables present
- [x] Step 2 — `docker compose up -d`: `docker/docker-compose.yml` exists, correct file path
- [x] Step 3 — Initialize DB: `infrastructure/scripts/migrate.py` exists; `DATABASE_URL` env var used
- [x] Step 4 — Seed knowledge base: `infrastructure/scripts/seed_knowledge_base.py` exists; `--knowledge-dir` flag confirmed in script argparse
- [x] Step 5 — Create test user: `infrastructure/scripts/create_user.py` exists; `--user-id` and `--role` flags confirmed
- [x] Step 6 — VM provisioning flow: `POST /api/v1/requests` and `POST /api/v1/jobs/{job_id}/confirm` routes exist in `web/backend/routers/`
- [x] Step 7 — FAQ flow: `faq` intent branch in orchestrator and web router confirmed
- [x] Step 8 — Run tests: all pytest commands match CLAUDE.md
- [x] Step 9 — Observability URLs: verified against docker-compose.yml service definitions
- [x] Step 10 — Useful commands: updated to include `-f docker/docker-compose.yml`

---

## Ports Reference (canonical)

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
