# Quickstart: Infra Q&A UI – ReactJS Frontend

**Phase 1 output** | **Date**: 2026-05-15

---

## Prerequisites

- Node 20 LTS installed (`node --version` should print `v20.x.x`)
- The full backend stack running (see `specs/001-agentic-infraops-platform/quickstart.md`)
- An API key for a valid user (create one with `python infrastructure/scripts/create_user.py`)

---

## 1. Install dependencies

```bash
cd web/frontend
npm install
```

---

## 2. Configure environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_API_KEY=<your-api-key>
```

`VITE_API_KEY` is the plaintext key returned by `create_user.py`. It is injected at build time — never committed to source control.

---

## 3. Start the development server

```bash
npm run dev
```

Opens at `http://localhost:5173` by default. The dev server proxies `/api` requests to `VITE_API_BASE_URL` to avoid CORS issues in local development.

---

## 4. Run tests

```bash
# Unit + component tests
npm run test

# Tests with coverage
npm run test -- --coverage

# E2E smoke test (requires the backend stack running)
npm run test:e2e
```

---

## 5. Build for production

```bash
npm run build
```

Output in `dist/`. The build bakes in the env vars from `.env.local` (or CI environment).

---

## 6. Run via Docker Compose

The frontend is included in the main Docker Compose stack as service `web-frontend`:

```bash
# From repo root
docker compose -f docker/docker-compose.yml --env-file .env up -d web-frontend
```

Access at `http://localhost:3001`.

To rebuild after a code change:

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d --no-deps --build web-frontend
```

---

## 7. Verify the setup

1. Open `http://localhost:5173` (dev) or `http://localhost:3001` (Docker)
2. Check the header shows your `user_id` and `role` (populated from `GET /auth/me`)
3. Type a question such as `What is the status of vm-web-01?` and press Enter
4. Confirm an intent confirmation card appears before the result renders
5. Click "Looks right, continue" and verify the enquiry result displays

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Header shows no user / role | `VITE_API_KEY` is missing or invalid; check `.env.local` |
| All requests return 401 | API key not set or wrong; recreate with `create_user.py` |
| SSE stream never updates | Backend stack not fully started; check `docker compose logs provisioning-agent` |
| "Something went wrong" on every submit | `VITE_API_BASE_URL` points to wrong host/port; check `.env.local` |
| Dark mode resets on refresh | `localStorage` may be disabled by browser privacy settings |
