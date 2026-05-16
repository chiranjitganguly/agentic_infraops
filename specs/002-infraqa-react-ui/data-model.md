# Data Model: Infra Q&A UI – ReactJS Frontend

**Phase 1 output** | **Date**: 2026-05-15

This document covers the client-side data model only. No new database tables or backend schemas are introduced. All persistence is in browser memory (session-scoped) or `localStorage` (theme preference).

---

## Entities

### Conversation

The top-level session container. At most 5 `Conversation` objects are retained per browser session. When a 6th is created, the oldest (by `created_at`) is evicted.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` (UUID) | Client-generated identifier |
| `title` | `string` | Auto-derived from the first user message (truncated to 48 chars) |
| `created_at` | `Date` | Wall-clock time when the conversation was started |
| `messages` | `Message[]` | Ordered list of messages, oldest first |
| `trace` | `AgentTraceEntry[]` | Last captured trace snapshot; empty array if no trace received |
| `active_job_id` | `string \| null` | `job_id` of the in-flight provisioning job, if any |

**Invariants**:
- `messages.length >= 1` for any non-empty conversation
- `trace` is replaced (not appended) when a new response with trace data arrives
- `active_job_id` is cleared when the provisioning SSE stream reaches a terminal state

---

### Message

A single exchange unit within a `Conversation`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` (UUID) | Client-generated |
| `role` | `'user' \| 'assistant' \| 'system'` | Origin of the message |
| `content` | `string` | Plain-text content |
| `created_at` | `Date` | Wall-clock time |
| `intent` | `'provision' \| 'enquiry' \| 'faq' \| null` | Set on assistant messages after routing |
| `infra_request_id` | `string \| null` | Set on assistant messages from backend `infra_request_id` |
| `confirmation` | `IntentConfirmation \| null` | Non-null for provisioning/enquiry assistant messages requiring confirmation |
| `clarification` | `ClarificationPayload \| null` | Non-null when `status === 'clarification_needed'` |
| `error` | `ErrorPayload \| null` | Non-null when the backend returned a 4xx/5xx |
| `job_statuses` | `JobStatusUpdate[]` | Accumulated provisioning SSE events; grows as stream arrives |

---

### IntentConfirmation

Attached to an assistant `Message` for provisioning and enquiry intents. Governs Intent Confirmation Card rendering.

| Field | Type | Description |
|-------|------|-------------|
| `intent_summary` | `string \| null` | Plain-language restatement from backend (`intent_summary` field); null until backend extension is deployed |
| `intent` | `'provision' \| 'enquiry'` | Determines card variant |
| `confidence` | `number \| null` | Orchestrator confidence score (0–1); shown as low-confidence badge if < 0.7 |
| `job_id` | `string \| null` | Present for provisioning; used for confirm/cancel calls |
| `confirmation_summary` | `Record<string, unknown> \| null` | GCP parameter map from backend; rendered as key/value pairs |
| `expires_at` | `string \| null` | ISO-8601 expiry for provisioning countdown |
| `confirmed` | `boolean` | Set to true after user clicks "Looks right, continue" |
| `cancelled` | `boolean` | Set to true after user clicks "Rephrase" or countdown expires |

---

### ClarificationPayload

Attached to an assistant `Message` when the backend returns `status: 'clarification_needed'`.

| Field | Type | Description |
|-------|------|-------------|
| `infra_request_id` | `string` | Passed to `POST /requests/{infra_request_id}/clarify` |
| `question` | `string` | Orchestrator's clarification question, displayed verbatim |
| `round` | `number` | 1 or 2; after round 2 the backend rejects rather than asking again |
| `answered` | `boolean` | True after the user submits an answer |

---

### AgentTraceEntry

One agent's execution record within a request.

| Field | Type | Description |
|-------|------|-------------|
| `agent_name` | `string` | Display name of the agent |
| `role` | `string \| null` | Short role description, if provided by backend |
| `status` | `'pending' \| 'running' \| 'completed' \| 'failed'` | Current execution state |
| `duration_ms` | `number \| null` | Elapsed time; shown if provided |

---

### JobStatusUpdate

A single SSE `event: status` payload received from `GET /jobs/{job_id}/stream`.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `string` | Matches the provisioning job |
| `status` | `JobStatus` | One of the canonical ProvisioningJob states |
| `received_at` | `Date` | Client-side timestamp of receipt |

**JobStatus** (union type):
```typescript
type JobStatus =
  | 'awaiting_confirmation'
  | 'queued'
  | 'in_progress'
  | 'retrying'
  | 'rollback'
  | 'succeeded'
  | 'failed'
  | 'cancelled';
```

---

### ErrorPayload

Attached to an assistant `Message` when the backend returns a 4xx or 5xx.

| Field | Type | Description |
|-------|------|-------------|
| `error_code` | `string` | `GUARDRAIL_VIOLATION`, `RATE_LIMIT_EXCEEDED`, `VALIDATION_ERROR`, or `INTERNAL_ERROR` |
| `message` | `string` | Backend message (verbatim for 4xx); generic fallback for 5xx |
| `http_status` | `number` | Original HTTP status code |

---

## Zustand Store Slices

### `conversations` slice

```
state:
  conversations: Conversation[]     // ordered newest-first, max 5
  active_conversation_id: string | null

actions:
  createConversation() → string     // generates id, evicts oldest if at cap, returns new id
  setActiveConversation(id)
  appendMessage(conv_id, message)
  updateMessage(conv_id, msg_id, partial)   // patch any field
  appendJobStatus(conv_id, msg_id, update)  // push to job_statuses
  updateTrace(conv_id, trace[])             // replace trace snapshot
```

**Eviction rule**: when `conversations.length === 5` and `createConversation()` is called, `conversations.pop()` (the last = oldest) is removed before the new one is prepended.

---

### `user` slice

```
state:
  user_id: string | null
  role: 'developer' | 'platform_engineer' | null
  daily_provisioning_count: number
  daily_provisioning_limit: number
  loaded: boolean

actions:
  setUser(payload from GET /auth/me)
  incrementDailyCount()             // called after provisioning job queued
```

---

### `theme` slice

```
state:
  theme: 'light' | 'dark'

actions:
  toggleTheme()
```

Persisted to `localStorage` key `infraops-ui-theme` via `zustand/middleware/persist`.

---

## State Transitions

### Provisioning Intent Flow

```
User submits query
  → Message appended (role: user)
  → Async POST /requests
  → Assistant message appended (role: assistant, intent: null, loading)
  → 202 response received
  → Message updated: intent='provision', confirmation={...}, infra_request_id, job_id, expires_at
  → IntentConfirmationCard rendered

User clicks "Looks right, continue"
  → confirmation.confirmed = true (button disabled)
  → POST /jobs/{job_id}/confirm
  → EventSource opened on GET /jobs/{job_id}/stream
  → job_statuses updated on each SSE 'status' event
  → SSE 'done' event → stream closed, active_job_id cleared

User clicks "Rephrase"
  → POST /jobs/{job_id}/cancel
  → confirmation.cancelled = true
  → Input restored with original query text

Countdown reaches zero
  → confirm button disabled
  → POST /jobs/{job_id}/cancel
  → expiry message shown
  → confirmation.cancelled = true
```

### Clarification Loop Flow

```
POST /requests → 200, status: 'clarification_needed'
  → Assistant message: clarification={question, infra_request_id, round: 1}
  → ClarificationCard rendered inline

User submits answer
  → POST /requests/{infra_request_id}/clarify
  → clarification.answered = true
  → follow-up response handled by same intent router

Second clarification round fails
  → Backend returns 400 VALIDATION_ERROR
  → ErrorPayload appended to message
  → Input re-enables for fresh query
```

---

## Out of Scope (Data Model)

- No IndexedDB or service worker caching
- No server-side session tokens or cookies
- No WebSocket connection (SSE only)
- No multi-user shared state
