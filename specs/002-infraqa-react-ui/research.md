# Research: Infra Q&A UI – ReactJS Frontend

**Phase 0 output** | **Date**: 2026-05-15

---

## 1. SSE Event Schema (`GET /jobs/{job_id}/stream`)

**Decision**: Two event types emitted by the backend SSE endpoint.

Confirmed from `web/backend/routers/sse.py` (lines 60–63):

```
event: status
data: {"job_id": "<uuid>", "status": "<job_status>"}

event: done
data: (empty string)
```

Status values (from `_TERMINAL_STATUSES` in sse.py + ProvisioningJob state machine in CONTEXT.md):
- Non-terminal: `queued`, `in_progress`, `retrying`, `rollback`
- Terminal (trigger `event: done`): `completed`, `succeeded`, `failed`, `rolled_back`, `cancelled`

**Reconnect strategy**: Native `EventSource` closes on error; the hook must detect close, increment attempt counter (max 3), and call `new EventSource(url)` after a brief delay. No server-side reconnect token needed — SSE state is reconstructed from the last rendered status.

**Rationale**: Backend streams status transitions only; the frontend accumulates and renders all received transitions. On reconnect, previously rendered statuses are preserved (FR-006).

---

## 2. API Response Shapes (confirmed from backend source)

### `POST /api/v1/requests` — provisioning intent (HTTP 202)

```json
{
  "infra_request_id": "<uuid>",
  "job_id": "<uuid>",
  "intent": "provision",
  "status": "awaiting_confirmation",
  "confirmation_summary": { ... },
  "expires_at": "<ISO-8601>",
  "correlation_id": "<uuid>"
}
```

**Gap**: `intent_summary` field is absent. Backend extension required before FR-007 / FR-007a can be implemented (spec: Backend Extension Required section).

### `POST /api/v1/requests` — enquiry intent (HTTP 200)

```json
{
  "infra_request_id": "<uuid>",
  "intent": "enquiry",
  "query_type": "single" | "list",
  "status": "answered",
  "answer": "<string>",
  "queried_at": "<ISO-8601>",
  "correlation_id": "<uuid>",
  "resource_type": "<string>",
  "resource_name": "<string>",        // single only
  "gcp_status": "<string>",           // single only
  "metadata": { ... },                // single only
  "resources": [ ... ],               // list only
  "total_count": <int>                // list only
}
```

**Gap**: `intent_summary` field absent (same backend extension required).

### `POST /api/v1/requests` — FAQ intent (HTTP 200)

```json
{
  "infra_request_id": "<uuid>",
  "intent": "faq",
  "status": "answered",
  "answer": "<string>",
  "sources": [ "<string>", ... ],
  "correlation_id": "<uuid>"
}
```

### `POST /api/v1/requests` — clarification_needed (HTTP 200)

```json
{
  "infra_request_id": "<uuid>",
  "status": "clarification_needed",
  "clarification_question": "<string>",
  "correlation_id": "<uuid>"
}
```

Clarify endpoint additionally returns `clarification_round: <int>` (1 or 2).

### Error responses (403 / 429 / 400)

```json
{
  "error_code": "GUARDRAIL_VIOLATION" | "RATE_LIMIT_EXCEEDED" | "VALIDATION_ERROR",
  "message": "<string>",
  "details": { ... },
  "correlation_id": null | "<uuid>",
  "timestamp": "<ISO-8601>"
}
```

### `GET /auth/me` (HTTP 200)

```json
{
  "user_id": "<string>",
  "role": "developer" | "platform_engineer",
  "api_key_expires_at": "<ISO-8601>" | null,
  "daily_provisioning_count": <int>,
  "daily_provisioning_limit": <int>
}
```

### `POST /jobs/{job_id}/confirm` (HTTP 200)

```json
{
  "job_id": "<uuid>",
  "status": "queued",
  "message": "<string>",
  "correlation_id": "<uuid>"
}
```

### `POST /jobs/{job_id}/cancel` (HTTP 200)

```json
{
  "job_id": "<uuid>",
  "status": "cancelled",
  "correlation_id": "<uuid>"
}
```

---

## 3. State Management Approach

**Decision**: Zustand (not Context API).

**Rationale**: The conversation store needs to handle cross-component mutations (sidebar + chat + trace panel all read the same Conversation list), atomic eviction (5-cap), and async SSE status patching. Zustand's flat, subscription-based model handles this without prop-drilling or complex reducer boilerplate. Context API would work but produces excessive re-renders when streaming trace events update frequently.

**Alternatives considered**: Redux Toolkit (rejected — too much boilerplate for session-scoped state with no persistence requirement), Context API (rejected — performance concern during high-frequency SSE updates).

---

## 4. SSE Reconnect Implementation

**Decision**: Custom `useJobStream` hook wrapping native `EventSource`.

```
- Open EventSource(url, { withCredentials: false })
- On 'status' event: append status to job status list in store
- On 'done' event: mark stream complete, close EventSource
- On EventSource 'error': close existing connection, increment attempt counter
  - If attempt ≤ 3: wait 1s * attempt (linear backoff), open new EventSource
  - If attempt > 3: set reconnect_failed = true, surface manual retry button
- Preserve all previously received statuses on reconnect
```

**Rationale**: Native `EventSource` does not auto-reconnect in a controlled way (browser reconnect ignores attempt limits). Custom hook provides the 3-attempt cap required by FR-006. Linear backoff (1s, 2s, 3s) is lightweight and avoids long delays for a transient network hiccup.

**Alternatives considered**: `reconnecting-eventsource` npm package (rejected — adds a dependency for minimal logic that the spec already specifies precisely).

---

## 5. Countdown Timer

**Decision**: Client-side countdown from `expires_at` ISO-8601 string using `useCountdown` hook + `setInterval`.

**Sequence on expiry** (from spec FR-007 and CONTEXT.md): disable confirm button → call `POST /jobs/{job_id}/cancel` → show expiry message.

The hook fires a callback at T=0; the callback performs the disable-then-cancel-then-message sequence in order. The confirm button is controlled by a `disabled` prop so the button state updates synchronously before the async cancel call completes.

---

## 6. Theme Persistence

**Decision**: Zustand `theme` store persisted to `localStorage` via `zustand/middleware/persist`.

Key: `infraops-ui-theme`. Value: `"light"` | `"dark"`.

On load: read from localStorage → apply `dark` class to `<html>` element. TailwindCSS `darkMode: 'class'` strategy.

---

## 7. Trace Data Model in the Frontend

**Decision**: Trace data is a structured array of `AgentTraceEntry` objects, persisted in the session-scoped `Conversation` object in the Zustand store.

- For provisioning: trace events may arrive via SSE (if the backend sends them) or via the initial confirmation response.
- For FAQ/enquiry: trace arrives in the complete JSON response body.
- On sidebar revisit: the trace stored in the Conversation object is rendered directly (no re-fetch needed — FR-013a).

The backend does not currently define a formal trace schema. The frontend treats trace as `Array<{ agent_name: string, role?: string, status: 'pending' | 'running' | 'completed' | 'failed', duration_ms?: number }>`. If trace is absent from the response, the trace panel shows "No trace available" (spec edge case).

---

## 8. Docker Delivery

**Decision**: Multi-stage Dockerfile — Node 20 Alpine build stage, nginx Alpine runtime stage.

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ARG VITE_API_KEY
RUN npm run build

FROM nginx:alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

nginx.conf: SPA fallback (`try_files $uri /index.html`), gzip enabled, static asset caching.

Added to `docker/docker-compose.yml` as service `web-frontend` on port `3001` (does not conflict with existing Grafana on `3000`).

**Rationale**: Satisfies Constitution Principle XV. The build-time env vars (`VITE_API_KEY`, `VITE_API_BASE_URL`) are baked into the Vite bundle — they are not injected at runtime, consistent with the spec's auth model (no login page, static bearer token).

---

## 9. Unresolved Items Deferred to Implementation

- Exact shape of `confirmation_summary` object from provisioning agent — rendered as key/value pairs from whatever the backend returns; no hardcoded field list.
- Trace event schema for provisioning SSE — if/when the backend adds `event: trace` events, the `useJobStream` hook will need a handler. Not required for initial delivery.
- `intent_summary` backend field — frontend should degrade gracefully if the field is absent (show empty or omit the intent restatement line) until the backend extension is deployed.
