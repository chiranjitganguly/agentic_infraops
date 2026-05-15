# Tasks: Infra Q&A UI – ReactJS Frontend

**Input**: Design documents from `specs/002-infraqa-react-ui/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. No test tasks are included unless noted — the spec does not mandate TDD. Vitest component/unit tests are included selectively where logic is non-trivial (store eviction, countdown, hooks).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)
- All paths are relative to the repository root

---

## Phase 1: Setup

**Purpose**: Scaffold the React project, configure tooling, and wire the Docker delivery model. No application logic.

- [x] T001 Initialise Vite + React + TypeScript project in `web/frontend/` (`npm create vite@latest . -- --template react-ts`); update `web/frontend/package.json` with `@types/react`, `@types/react-dom`, `zustand`, `@tanstack/react-query`, `tailwindcss`, `postcss`, `autoprefixer`
- [x] T002 Configure TailwindCSS with `darkMode: 'class'` strategy in `web/frontend/tailwind.config.ts` and `web/frontend/postcss.config.js`; add Tailwind directives to `web/frontend/src/index.css`
- [x] T003 [P] Configure Vitest and React Testing Library in `web/frontend/vite.config.ts` (add `test` block) and `web/frontend/src/setupTests.ts` (`@testing-library/jest-dom` import)
- [x] T004 [P] Configure Playwright for E2E smoke tests in `web/frontend/playwright.config.ts` (baseURL: `http://localhost:5173`, single Chromium project)
- [x] T005 [P] Create `web/frontend/src/env.d.ts` declaring `ImportMetaEnv` with `VITE_API_BASE_URL: string` and `VITE_API_KEY: string`
- [x] T006 [P] Create `web/frontend/.env.example` with `VITE_API_BASE_URL=http://localhost:8000/api/v1` and `VITE_API_KEY=<your-api-key>` placeholders
- [x] T007 Create multi-stage `web/frontend/Dockerfile` (Node 20 Alpine build stage baking in `VITE_API_BASE_URL` and `VITE_API_KEY` ARGs, nginx Alpine runtime stage serving `dist/`)
- [x] T008 [P] Create `web/frontend/nginx.conf` with SPA fallback (`try_files $uri /index.html`), gzip enabled, 1-year cache for hashed static assets
- [x] T009 Add `web-frontend` service to `docker/docker-compose.yml` (build context: `web/frontend`, port `3001:80`, depends_on `web-backend`, pass `VITE_API_BASE_URL` and `VITE_API_KEY` as build args)
- [x] T010 [P] Copy TypeScript API contract types from `specs/002-infraqa-react-ui/contracts/api.ts` into `web/frontend/src/types/api.ts`
- [x] T011 [P] Copy TypeScript entity types from `specs/002-infraqa-react-ui/contracts/entities.ts` into `web/frontend/src/types/entities.ts`

**Checkpoint**: Project builds (`npm run build`), Docker image builds, Vitest and Playwright configs present.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: API client, Zustand stores, auth hook, and AppShell layout. MUST complete before any user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T012 Create API fetch client in `web/frontend/src/api/client.ts` — typed `apiFetch` wrapper that reads `VITE_API_KEY` from `import.meta.env`, sets `Authorization: Bearer <key>` on every request, throws `ApiError` on non-2xx responses
- [x] T013 [P] Create auth API module in `web/frontend/src/api/auth.ts` — `getMe(): Promise<GetMeResponse>` calling `GET /auth/me` via the client
- [x] T014 [P] Create requests API module in `web/frontend/src/api/requests.ts` — `submitRequest(body: SubmitRequestBody): Promise<SubmitRequestResponse>` and `clarifyRequest(id, body: ClarifyBody): Promise<SubmitRequestResponse>`
- [x] T015 [P] Create jobs API module in `web/frontend/src/api/jobs.ts` — `confirmJob(jobId): Promise<ConfirmJobResponse>` and `cancelJob(jobId): Promise<CancelJobResponse>`
- [x] T016 Create conversations Zustand store in `web/frontend/src/store/conversations.ts` — state: `conversations: Conversation[]` (max 5, newest-first), `active_conversation_id: string | null`; actions: `createConversation`, `setActiveConversation`, `appendMessage`, `updateMessage`, `appendJobStatus`, `updateTrace`; eviction: when `conversations.length === 5`, `conversations.pop()` before prepending new one
- [x] T017 [P] Create user Zustand store in `web/frontend/src/store/user.ts` — state: `UserState`; actions: `setUser(GetMeResponse)`, `incrementDailyCount()`
- [x] T018 [P] Create theme Zustand store in `web/frontend/src/store/theme.ts` — state: `theme: Theme`; action: `toggleTheme()`; persisted to `localStorage` key `infraops-ui-theme` via `zustand/middleware/persist`; on hydration apply/remove `dark` class on `document.documentElement`
- [x] T019 Create `useAuth` hook in `web/frontend/src/hooks/useAuth.ts` — calls `getMe()` once on mount, populates user store; if call fails sets `loaded: true` with nulls (UI degrades gracefully)
- [x] T020 Create `AppShell` layout component in `web/frontend/src/components/layout/AppShell.tsx` — three-column shell: left sidebar slot (collapsed by default on mobile), main chat area slot, no right panel yet; uses Tailwind flex layout
- [x] T021 Wire `useAuth` in `web/frontend/src/App.tsx` and render `AppShell`; wrap with `QueryClientProvider` (`@tanstack/react-query`)
- [x] T022 [P] Create `Header` component in `web/frontend/src/components/layout/Header.tsx` — displays `user_id`, `role`, and `daily_provisioning_count / daily_provisioning_limit` from user store; ThemeToggle slot (wired in US5)
- [x] T023 [P] Create `ErrorMessage` shared component in `web/frontend/src/components/shared/ErrorMessage.tsx` — accepts `ErrorPayload`, renders the correct copy per error_code (FR-020a–d), neutral or warning visual style based on type
- [x] T024 [P] Create `LoadingIndicator` shared component in `web/frontend/src/components/shared/LoadingIndicator.tsx` — animated typing-dots indicator; used in MessageBubble while loading

**Checkpoint**: App renders in browser, header shows user_id from `GET /auth/me`, AppShell layout visible.

---

## Phase 3: User Story 1 — Submit a Query and Receive an Answer (Priority: P1) 🎯 MVP

**Goal**: User can type a natural-language question, submit it, see a loading indicator, then receive and read the complete answer. Covers FAQ and enquiry intent responses and all four error states (FR-001–FR-005, FR-020, FR-020a–d, SC-001, SC-002, SC-008).

**Independent Test**: Open the app, type "What is the best practice for VPC design on GCP?", press Enter, verify a loading indicator appears then a complete answer renders. Type an invalid request that triggers a 400, verify inline error message appears and input re-enables without page reload.

- [x] T025 [US1] Create `InputComposer` component in `web/frontend/src/components/chat/InputComposer.tsx` — multiline `<textarea>` (Shift+Enter = newline, Enter = submit), disabled when `loading` prop is true, empty-input guard (shake animation or subtle hint), `onSubmit(text: string)` callback
- [x] T026 [US1] Create `MessageBubble` component in `web/frontend/src/components/chat/MessageBubble.tsx` — renders user messages (right-aligned), assistant messages (left-aligned); slots for: loading state (shows `LoadingIndicator`), FAQ answer (answer + sources list), enquiry answer (answer + resource details), error state (shows `ErrorMessage`); reads `Message` type from entities
- [x] T027 [US1] Create `MessageList` component in `web/frontend/src/components/chat/MessageList.tsx` — renders `MessageBubble` for each message in the active conversation; auto-scrolls to bottom when messages length changes (FR-003)
- [x] T028 [US1] Create `ChatWindow` component in `web/frontend/src/components/chat/ChatWindow.tsx` — composes `MessageList` + `InputComposer`; passes `onSubmit` from `useSubmitRequest`; disables InputComposer while `isLoading` is true
- [x] T029 [US1] Implement `useSubmitRequest` hook in `web/frontend/src/hooks/useSubmitRequest.ts` — creates new message (role: user), appends to store, calls `submitRequest()`, appends loading assistant message, on response: routes by `intent` field: `faq` → render answer+sources; `enquiry` → render answer+resource data; `clarification_needed` → hand off to clarification handler; any 4xx/5xx → set `error` on message; always re-enables input after response
- [x] T030 [P] [US1] Implement FAQ response rendering in `MessageBubble.tsx` — display `answer` text and `sources` array as a collapsible "Sources" list below the answer
- [x] T031 [P] [US1] Implement enquiry response rendering in `MessageBubble.tsx` — display `answer` text; for `query_type: 'single'` also show `resource_name`, `gcp_status`; for `query_type: 'list'` show `total_count` and `resources` count
- [x] T032 [US1] Implement all four error state renderers in `MessageBubble.tsx` per FR-020a–d: GUARDRAIL_VIOLATION → warning style + verbatim backend message + "contact platform engineer"; RATE_LIMIT_EXCEEDED → warning style + "Your daily provisioning limit resets at midnight UTC." + current count; VALIDATION_ERROR → neutral style + backend message + invite to rephrase; INTERNAL_ERROR/network → neutral style + "Something went wrong — please try again" (no raw detail exposed); input re-enables after all errors
- [x] T033 [US1] Wire `ChatWindow` into `AppShell` main area and connect `useSubmitRequest` in `web/frontend/src/App.tsx`; confirm submit → user message appears → loading indicator → assistant message renders; verify submit button disabled during loading
- [x] T034 [P] [US1] Write Vitest unit tests for `useSubmitRequest` in `web/frontend/tests/unit/hooks/useSubmitRequest.test.ts` — mock `submitRequest`, test FAQ path (answer rendered), test 4xx error path (ErrorPayload set), test input-disabled-while-loading invariant
- [x] T035 [P] [US1] Write Vitest component tests for `MessageBubble` error variants in `web/frontend/tests/components/MessageBubble.test.tsx` — render each of the four error codes and assert correct copy and style class present

**Checkpoint**: Full FAQ ask-and-answer loop works. Enquiry answers render. All four error states show inline. Input re-enables after every response.

---

## Phase 4: User Story 2 — Intent Confirmation and Provisioning SSE (Priority: P2)

**Goal**: Provisioning and enquiry queries show an intent confirmation card before the result renders. Provisioning jobs open an SSE stream after confirmation. Clarification loop renders inline cards. (FR-006, FR-006a–c, FR-007, FR-007a–c, FR-008, SC-001, SC-005)

**Independent Test**: Submit "Create a VM named vm-test-01 with 4 CPUs in us-central1" — verify a merged confirmation card appears with intent_summary + GCP params + countdown, no result shown yet. Click "Looks right, continue" — verify job status updates arrive via SSE. Submit a low-confidence query — verify a clarification card appears with a text input.

- [x] T036 [US2] Create `CountdownTimer` component in `web/frontend/src/components/shared/CountdownTimer.tsx` — accepts `expiresAt: string` (ISO-8601) and `onExpired: () => void`; displays MM:SS countdown; fires `onExpired` callback when reaching zero
- [x] T037 [US2] Implement `useCountdown` hook in `web/frontend/src/hooks/useCountdown.ts` — `setInterval`-based countdown from `expires_at`; returns `{ secondsLeft, isExpired }`; clears interval on unmount; used by `CountdownTimer`
- [x] T038 [US2] Create `IntentConfirmationCard` component in `web/frontend/src/components/cards/IntentConfirmationCard.tsx` — provisioning variant: shows `intent_summary` (or empty if absent from backend — graceful degradation), `confirmation_summary` key/value pairs, `CountdownTimer`, "Looks right, continue" button (disabled on expiry or after click), "Rephrase" button; visually distinct from MessageBubble (FR-008); low-confidence badge if `confidence < 0.7`
- [x] T039 [US2] Create `EnquiryConfirmationCard` component in `web/frontend/src/components/cards/EnquiryConfirmationCard.tsx` — lightweight variant: shows `intent_summary`, "Looks right, continue" and "Rephrase" buttons; no countdown, no parameter summary; visually distinct from MessageBubble
- [x] T040 [US2] Create `ClarificationCard` component in `web/frontend/src/components/cards/ClarificationCard.tsx` — displays orchestrator's clarification question verbatim, single-line text input, "Submit answer" button; rendered inline below the user's original message; visually distinct from both IntentConfirmationCard and MessageBubble (FR-006a)
- [x] T041 [US2] Create SSE EventSource wrapper in `web/frontend/src/api/sse.ts` — `openJobStream(jobId, onStatus, onDone, onError)`: opens `EventSource` on `GET /jobs/{jobId}/stream`; dispatches `event: status` payloads to `onStatus(SseStatusEventData)`, `event: done` to `onDone()`, EventSource `error` to `onError()`; exposes `close()` method
- [x] T042 [US2] Implement `useJobStream` hook in `web/frontend/src/hooks/useJobStream.ts` — manages SSE lifecycle: opens stream after confirmation, appends each `JobStatusUpdate` to store via `appendJobStatus`, closes on `event: done` or terminal status; on EventSource error: increment attempt counter (max 3), reconnect after `attempt * 1000ms` linear backoff; if 3 attempts all fail: set `sseState: 'failed'`, surface retry button; preserves all previously received statuses on reconnect (FR-006)
- [x] T043 [US2] Wire provisioning intent routing in `useSubmitRequest.ts`: on 202 response, set `message.intent = 'provision'`, set `message.confirmation = { job_id, confirmation_summary, expires_at, intent_summary, intent: 'provision', confirmed: false, cancelled: false }`; `ChatWindow` renders `IntentConfirmationCard` for messages with `confirmation.intent === 'provision'`
- [x] T044 [US2] Implement "Looks right, continue" action for provisioning in `IntentConfirmationCard.tsx`: call `confirmJob(job_id)`, then open SSE stream via `useJobStream`; update `message.confirmation.confirmed = true`; `MessageBubble` renders `JobStatusUpdate` list as they arrive
- [x] T045 [US2] Wire enquiry intent routing in `useSubmitRequest.ts`: on 200 enquiry response, set `message.intent = 'enquiry'`, set `message.confirmation = { intent_summary, intent: 'enquiry', confirmed: false, cancelled: false, job_id: null, confirmation_summary: null, expires_at: null }`; `ChatWindow` renders `EnquiryConfirmationCard`; "Looks right, continue" sets `confirmation.confirmed = true` and renders the enquiry answer already present in the message (no new network call — FR-007a)
- [x] T046 [US2] Implement "Rephrase" action in `IntentConfirmationCard.tsx` and `EnquiryConfirmationCard.tsx`: for provisioning, call `cancelJob(job_id)` first; set `confirmation.cancelled = true`; restore original query text to `InputComposer` via store or callback (FR-007c)
- [x] T047 [US2] Implement countdown expiry sequence in `IntentConfirmationCard.tsx` driven by `CountdownTimer.onExpired`: (1) disable "Looks right, continue" button synchronously; (2) call `cancelJob(job_id)` async; (3) replace countdown area with expiry message "Confirmation expired — please start a new query"; in that strict order (FR-007)
- [x] T048 [US2] Implement clarification loop in `useSubmitRequest.ts` and `ClarificationCard.tsx`: on `clarification_needed` response set `message.clarification = { infra_request_id, question, round, answered: false }`; ChatWindow renders ClarificationCard; submitting answer calls `clarifyRequest(infra_request_id, { clarification: answer })`, sets `clarification.answered = true`, handles follow-up response through same intent router; on second round failure (400 from backend) render `ErrorPayload` and re-enable input (FR-006a–c)
- [x] T049 [P] [US2] Write Vitest unit tests for `useCountdown` in `web/frontend/tests/unit/hooks/useCountdown.test.ts` — mock timers: verify `onExpired` fires at zero, verify `isExpired` true after expiry, verify button disabled before `cancelJob` call
- [x] T050 [P] [US2] Write Vitest component tests for `IntentConfirmationCard` in `web/frontend/tests/components/IntentConfirmationCard.test.tsx` — render with provisioning payload; click "Looks right, continue" → confirm button disabled; countdown expiry mock → disable → cancel called → expiry message shown; "Rephrase" → cancel called → input restored

**Checkpoint**: Provisioning queries show merged confirmation card, SSE stream updates job statuses, enquiry shows lightweight card, clarification loop renders inline, all expiry and rephrase paths work correctly.

---

## Phase 5: User Story 3 — Agent Execution Trace (Priority: P3)

**Goal**: Collapsible trace panel shows agent invocation sequence with real-time status updates. Trace snapshot persists when revisiting a past conversation. (FR-012–FR-014, SC-006)

**Independent Test**: Submit a query, expand the trace panel, verify ordered agent entries with status badges update. Collapse and re-expand. Switch to a past conversation in the sidebar, verify trace still shows.

- [x] T051 [US3] Create `AgentTraceEntry` component in `web/frontend/src/components/trace/AgentTraceEntry.tsx` — displays `agent_name`, `role` (if present), status badge (pending/running/completed/failed with distinct colours), `duration_ms` if present; failed status visually distinct (red or error icon)
- [x] T052 [US3] Create `TracePanel` component in `web/frontend/src/components/trace/TracePanel.tsx` — collapsible drawer or inline below response; lists `AgentTraceEntry` components from conversation trace; shows "No trace available" placeholder when `trace` array is empty (FR-012); smooth open/close animation
- [x] T053 [US3] Implement trace rendering for FAQ/enquiry responses in `useSubmitRequest.ts`: if response body contains a `trace` array, call `updateTrace(convId, trace)` after storing the message; `TracePanel` reads from `conversation.trace`
- [x] T054 [US3] Implement trace snapshot persistence for provisioning in `useJobStream.ts`: if SSE `status` events include trace fields, call `updateTrace(convId, trace)`; the snapshot in the Conversation object is the source of truth when revisiting via sidebar (FR-013a)
- [x] T055 [US3] Handle absent trace gracefully: if no `trace` field in response, store `trace: []`; `TracePanel` renders "No trace available" placeholder — no broken/empty panel
- [x] T056 [P] [US3] Write Vitest component tests for `TracePanel` in `web/frontend/tests/components/TracePanel.test.tsx` — render with populated trace (3 entries, mixed statuses); render with empty trace (placeholder shown); toggle expand/collapse

**Checkpoint**: Trace panel renders for all intent types, updates live for provisioning, persists on sidebar revisit, degrades gracefully when trace absent.

---

## Phase 6: User Story 4 — Conversation History (Priority: P3)

**Goal**: Left sidebar lists up to 5 session-scoped conversations. User can switch between them and start new ones. Sidebar collapses on mobile. (FR-009, FR-009a, FR-010, FR-011, FR-018, SC-007)

**Independent Test**: Start two conversations, click the first in the sidebar, verify older messages restore. Create 6 conversations, verify only 5 remain. On a narrow viewport, verify sidebar is hidden by default.

- [x] T057 [US4] Create `Sidebar` component in `web/frontend/src/components/layout/Sidebar.tsx` — renders ordered conversation list (newest-first) from conversations store; each entry shows auto-title (truncated), highlights active conversation; "New Conversation" button in sidebar header; collapsed/expanded state driven by `AppShell` responsive logic
- [x] T058 [US4] Implement conversation switching in `Sidebar.tsx`: clicking an entry calls `setActiveConversation(id)`; `ChatWindow` reads messages from the now-active conversation in the store — no re-fetch needed (FR-010)
- [x] T059 [US4] Implement "New Conversation" button action in `Sidebar.tsx`: calls `createConversation()` in store (which handles 5-cap eviction), sets it active, `ChatWindow` renders empty state; previous conversation preserved in sidebar (FR-009a)
- [x] T060 [US4] Implement 5-cap eviction in `web/frontend/src/store/conversations.ts`: when `conversations.length === 5` before adding new one, `conversations.splice(conversations.length - 1, 1)` (remove oldest/last); add unit test assertion in T062
- [x] T061 [US4] Implement auto-generated title in conversations store `createConversation` / first message flow in `web/frontend/src/store/conversations.ts`: derive title from first user message content, truncated to 48 characters; update `conversation.title` when first user message appended (FR-011)
- [x] T062 [US4] Implement mobile sidebar collapse in `AppShell.tsx` and `Sidebar.tsx`: sidebar hidden by default (`hidden md:flex`) on viewports below `md` breakpoint; hamburger toggle button visible on mobile (`md:hidden`) opens/closes sidebar as overlay (FR-018)
- [x] T063 [P] [US4] Write Vitest unit tests for conversations store in `web/frontend/tests/unit/store/conversations.test.ts` — test 5-cap eviction (6th conversation drops oldest), title generation (truncated at 48 chars), `setActiveConversation` changes active id

**Checkpoint**: Sidebar shows up to 5 conversations, switching works, new conversation creates fresh thread, 5-cap enforced, sidebar collapses on mobile.

---

## Phase 7: User Story 5 — Theme Toggle (Priority: P4)

**Goal**: Light/dark theme toggle accessible from header, persists across sessions, WCAG AA compliant in both modes. (FR-015–FR-017, SC-003)

**Independent Test**: Click theme toggle, verify dark mode activates across all visible components. Refresh page, verify dark mode restored. Inspect contrast ratios in both modes.

- [x] T064 [US5] Create `ThemeToggle` component in `web/frontend/src/components/shared/ThemeToggle.tsx` — sun icon (light mode) / moon icon (dark mode) button; calls `toggleTheme()` from theme store on click; icons from a lightweight icon library (e.g. `lucide-react`)
- [x] T065 [US5] Wire `ThemeToggle` into `Header.tsx`; ensure `toggleTheme()` applies/removes `dark` class on `document.documentElement` synchronously; theme store persist middleware writes `infraops-ui-theme` to localStorage; on app load, `useEffect` in `App.tsx` reads localStorage and applies class before first paint (FR-015, FR-016)
- [x] T066 [US5] Audit all Tailwind colour tokens used across components for WCAG AA contrast compliance in `web/frontend/tailwind.config.ts`: ensure text-on-background contrast ≥ 4.5:1 in both `light` and `dark` variants for all text elements and interactive states (FR-017, SC-003)
- [x] T067 [P] [US5] Write Vitest unit tests for theme store in `web/frontend/tests/unit/store/theme.test.ts` — toggle switches between light and dark; `persist` middleware writes to localStorage; reading back from localStorage restores correct theme; `dark` class applied to `document.documentElement`

**Checkpoint**: Theme toggle works, dark mode persists on refresh, no contrast failures in either mode.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Responsive layout audit, accessibility pass, SSE retry surface, E2E smoke test, quickstart validation.

- [x] T068 Audit and fix responsive layout at all three breakpoints (mobile 320px, tablet 768px, desktop 1280px) in `web/frontend/src/components/layout/AppShell.tsx` — verify no horizontal scrolling at 320px, sidebar toggleable, input area fully operable (FR-019, SC-004)
- [x] T069 [P] Add `aria-label` attributes, `role` attributes, and semantic HTML (`<main>`, `<nav>`, `<aside>`, `<section>`) to all layout and interactive components across `web/frontend/src/components/` — keyboard navigation: Tab through InputComposer, confirm buttons, sidebar entries, theme toggle
- [x] T070 [P] Surface SSE reconnect state in `MessageBubble.tsx`: when `sseState === 'reconnecting'` show "reconnecting…" inline below latest status update; when `sseState === 'failed'` show manual retry button that calls `useJobStream.retry()` (FR-006)
- [x] T071 Write Playwright E2E smoke test in `web/frontend/tests/e2e/smoke.spec.ts` — test: open app → header shows user_id → type FAQ question → press Enter → loading indicator → answer renders → click theme toggle → dark class present on `<html>` → verify no console errors
- [x] T072 [P] Validate `specs/002-infraqa-react-ui/quickstart.md` by running all commands end-to-end: `npm install`, `npm run dev` (app loads), `npm run test` (passes), `npm run build` (dist generated), `docker build` with dummy ARGs (image builds); document any corrections needed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1 P1)**: Depends on Phase 2 — first deliverable, MVP scope
- **Phase 4 (US2 P2)**: Depends on Phase 3 (needs MessageBubble, useSubmitRequest)
- **Phase 5 (US3 P3)**: Depends on Phase 2; can be worked alongside Phase 4
- **Phase 6 (US4 P3)**: Depends on Phase 2; can be worked alongside Phases 4–5
- **Phase 7 (US5 P4)**: Depends on Phase 2 (needs Header, AppShell)
- **Phase 8 (Polish)**: Depends on all user story phases

### User Story Dependencies

- **US1 (P1)**: After Foundational — no story dependencies
- **US2 (P2)**: After US1 (needs MessageBubble and useSubmitRequest extension points)
- **US3 (P3)**: After Foundational — independent of US2; TracePanel is additive
- **US4 (P3)**: After Foundational — independent of US2/US3; Sidebar reads from store
- **US5 (P4)**: After Foundational — fully independent of all other stories

### Parallel Opportunities

- Phase 1: T003, T004, T005, T006, T008, T010, T011 can all run in parallel
- Phase 2: T013, T014, T015 (API modules) can run in parallel; T017, T018 (stores) can run in parallel after T016 is done
- Phase 3: T025–T028 (components) can run in parallel; T030, T031 can run in parallel
- Phase 4: T036–T040 (components) can run in parallel; T041 (SSE) independent
- Phase 5–7: All three user stories can run in parallel once Phase 2 is complete

---

## Parallel Example: Phase 2 Foundational

```bash
# These can be launched together (different files, no conflicts):
Task: "Create auth API module in web/frontend/src/api/auth.ts"              # T013
Task: "Create requests API module in web/frontend/src/api/requests.ts"     # T014
Task: "Create jobs API module in web/frontend/src/api/jobs.ts"             # T015
Task: "Create user Zustand store in web/frontend/src/store/user.ts"        # T017
Task: "Create theme Zustand store in web/frontend/src/store/theme.ts"      # T018
Task: "Create ErrorMessage component in web/frontend/src/components/..."    # T023
Task: "Create LoadingIndicator component in web/frontend/src/components/..." # T024
```

## Parallel Example: Phase 4 Intent Confirmation

```bash
# Component scaffolding (all different files):
Task: "Create CountdownTimer component"                 # T036
Task: "Create IntentConfirmationCard component"         # T038
Task: "Create EnquiryConfirmationCard component"        # T039
Task: "Create ClarificationCard component"              # T040
Task: "Create SSE EventSource wrapper"                  # T041
```

---

## Implementation Strategy

### MVP First (US1 Only — Phases 1–3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 (basic ask/answer loop with FAQ + error states)
4. **STOP and VALIDATE**: Type a FAQ question, verify answer renders; trigger 400 error, verify inline error and input re-enables
5. Demo to stakeholders — core value delivered

### Incremental Delivery

1. Phases 1–2 → Foundation ready
2. Phase 3 → FAQ + enquiry answers work → **Demo 1**
3. Phase 4 → Provisioning confirmation + SSE live updates + clarification → **Demo 2**
4. Phases 5–6 (parallel) → Trace panel + sidebar history → **Demo 3**
5. Phase 7 → Theme toggle → **Demo 4**
6. Phase 8 → Polish + E2E → **Release**

### Parallel Team Strategy (2 developers post-Foundational)

- Developer A: Phase 3 (US1) → Phase 4 (US2)
- Developer B: Phase 5 (US3) → Phase 6 (US4) → Phase 7 (US5)
- Merge after each phase completes; no shared file conflicts until Phase 8

---

## Notes

- `[P]` tasks = different files, no in-progress task dependencies — safe to run concurrently
- `intent_summary` from backend is absent until backend extension deployed; all confirmation card components must degrade gracefully when field is `null`/`undefined`
- SSE is exclusively for provisioning job status — never use `EventSource` for FAQ or enquiry responses
- The 5-conversation eviction happens in the store's `createConversation` action — not in the component
- Countdown expiry order is strict: disable button → cancel job → show expiry message (never rearrange)
- Trace snapshot is stored per Conversation object; it is replaced (not appended) when a new response with trace arrives
