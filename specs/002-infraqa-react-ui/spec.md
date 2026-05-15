# Feature Specification: Infra Q&A UI – ReactJS Frontend

**Feature Branch**: `002-infraqa-react-ui`
**Created**: 2026-05-15
**Status**: Draft

---

## Clarifications

### Session 2026-05-15

- Q: When an SSE connection drops mid-stream, what should the UI do? → A: Auto-reconnect silently up to 3 attempts, then show a manual retry button if still failing.
- Q: How does a user start a new conversation? → A: An explicit "New Conversation" button in the sidebar header creates a new thread.
- Q: Does the intent confirmation card require explicit user acknowledgement before the answer streams? → A: Yes — a "Looks right, continue" button must be clicked; the answer does not stream until confirmed.
- Q: Should the sidebar cap the number of conversations shown? → A: Retain last 5 conversations; oldest is dropped when the 6th is created.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Submit an Infrastructure Query and Receive a Streamed Answer (Priority: P1)

A developer opens the Q&A interface, types a natural-language infrastructure question, submits it, and watches the orchestrator's answer stream back word-by-word in real time. The interface remains responsive throughout, and the final response includes the sources or agents involved.

**Why this priority**: This is the core use case — every other feature depends on the basic ask-and-answer loop working correctly.

**Independent Test**: Open the app, type "What is the best practice for VPC design on GCP?", press Enter, and verify a streamed answer appears incrementally. Delivers a complete MVP on its own.

**Acceptance Scenarios**:

1. **Given** the user has the app open, **When** they type a question and press Enter (or click Submit), **Then** the question appears in the chat window and a loading indicator appears immediately.
2. **Given** the orchestrator is streaming a response, **When** tokens arrive, **Then** they render incrementally in the assistant's message bubble without the UI freezing.
3. **Given** the response is complete, **When** streaming ends, **Then** the loading indicator disappears and the input box becomes active again.
4. **Given** the backend is unreachable, **When** the user submits a question, **Then** a user-friendly error message appears and the input re-enables.
5. **Given** an active streaming response, **When** the user tries to submit another message, **Then** the submit button is disabled until streaming completes.

---

### User Story 2 — Review and Acknowledge Orchestrator Intent Confirmation (Priority: P2)

After submitting a non-FAQ query (provisioning or enquiry), the user sees an intent confirmation card showing how the orchestrator interpreted the request. The user must acknowledge it before the result is delivered. FAQ queries bypass this card entirely — the answer renders immediately.

**Why this priority**: Gives users confidence the system understood their request correctly before acting — especially critical for provisioning intents where a misread request could trigger infrastructure changes.

**Independent Test**: Submit an enquiry ("What is the status of vm-web-01?") and verify that an intent confirmation card appears before the result, requiring a click to proceed. Then submit a FAQ ("What is the best practice for VPC design?") and verify no card appears — the answer renders directly.

**Acceptance Scenarios**:

1. **Given** the user submits a provisioning query, **When** the orchestrator returns a provisioning intent with confirmation summary, **Then** a single confirmation card appears containing both the plain-language intent restatement and the full GCP parameter summary, with a 20-minute countdown timer, a "Looks right, continue" button, and a "Rephrase" option.
2. **Given** the user submits an enquiry query, **When** the orchestrator returns an enquiry intent, **Then** a lightweight confirmation card appears showing only the plain-language intent restatement (no parameter summary, no countdown), with "Looks right, continue" and "Rephrase" options.
3. **Given** the user submits a FAQ query, **When** the orchestrator returns a FAQ intent, **Then** no confirmation card appears — the answer renders directly.
4. **Given** a provisioning confirmation card is visible, **When** the user clicks "Looks right, continue", **Then** the job is confirmed and the provisioning SSE status stream begins.
5. **Given** an enquiry confirmation card is visible, **When** the user clicks "Looks right, continue", **Then** the enquiry result is rendered immediately (no further network call required).
6. **Given** either confirmation card is visible, **When** the user clicks "Rephrase", **Then** the card is dismissed, the original query is restored to the input field, the submit button re-enables, and any pending provisioning job is cancelled.
7. **Given** the intent classification returns low confidence (< 0.7), **When** the confirmation card is displayed, **Then** it clearly indicates the interpretation may be approximate (e.g., a visual badge or inline note).
8. **Given** a provisioning confirmation card is visible, **When** the 20-minute countdown expires, **Then** the "Looks right, continue" button is disabled first, then the UI calls `POST /jobs/{job_id}/cancel` to explicitly clean up the pending job, and finally an expiry message is shown — the user must start a new query.

---

### User Story 3 — View Agent Execution Trace and Orchestration Flow (Priority: P3)

The user can expand a collapsible panel alongside the response to see which agents were invoked, in what order, and their current status (running, completed, failed). Trace updates arrive in real time as the orchestration progresses.

**Why this priority**: Developer-centric observability — essential for debugging and building trust in the multi-agent system, but not needed for basic use.

**Independent Test**: Submit a query, open the trace panel, and verify it shows an ordered list of agents with their states updating live.

**Acceptance Scenarios**:

1. **Given** a query is processing, **When** the user expands the execution trace panel, **Then** they see each agent in the invocation chain with its current state (pending / running / completed / failed).
2. **Given** an agent transitions to completed, **When** the trace updates, **Then** the corresponding entry updates in real time without a page reload.
3. **Given** the trace panel is collapsed, **When** the user clicks to expand it, **Then** it opens smoothly without disrupting the chat area.
4. **Given** an agent fails, **When** it appears in the trace, **Then** it is visually distinguished (e.g., different colour or icon) from completed agents.
5. **Given** execution duration data is available, **When** an agent completes, **Then** the elapsed time is shown next to the agent entry.

---

### User Story 4 — Browse and Revisit Conversation History (Priority: P3)

The user sees a list of past conversations in the left sidebar. Clicking a past conversation restores the full message exchange in the main chat area.

**Why this priority**: Convenience for the current session — history is session-scoped only in this iteration, so loss on refresh is acceptable.

**Independent Test**: Start two conversations, click the first in the sidebar, and verify the older messages are restored in the main area.

**Acceptance Scenarios**:

1. **Given** the user has completed at least one conversation, **When** they look at the sidebar, **Then** they see a list of past conversations with short preview titles.
2. **Given** the sidebar shows past conversations, **When** the user clicks one, **Then** the main chat area switches to display that conversation's messages.
3. **Given** the user is on a mobile device, **When** they tap the sidebar toggle, **Then** the sidebar slides in or out without obscuring the main content.
4. **Given** a new conversation is started, **When** the user submits the first message, **Then** a new entry appears at the top of the sidebar history with the first message as its title.
5. **Given** the user clicks the "New Conversation" button, **When** the chat area clears, **Then** the previous conversation remains accessible in the sidebar and no data is lost.

---

### User Story 5 — Toggle Light and Dark Themes (Priority: P4)

The user can switch between light and dark modes using a toggle in the header. Their preference is remembered across sessions.

**Why this priority**: Polish and accessibility requirement — does not affect core functionality but important for extended use and compliance with accessibility standards.

**Independent Test**: Click the theme toggle, verify the interface switches to dark mode, refresh the page, and verify dark mode is still active.

**Acceptance Scenarios**:

1. **Given** the app loads, **When** no theme preference is saved, **Then** the system default (OS preference or light) is applied.
2. **Given** the user toggles the theme, **When** they refresh the page, **Then** their selected theme is restored.
3. **Given** dark mode is active, **When** inspecting contrast ratios, **Then** all text meets WCAG AA contrast minimums.
4. **Given** light mode is active, **When** inspecting contrast ratios, **Then** all text meets WCAG AA contrast minimums.

---

### Edge Cases

- What happens when the provisioning SSE stream drops mid-update? The UI silently attempts to reconnect up to 3 times (showing "reconnecting…"); if all attempts fail, a manual retry button appears and any status updates already shown are preserved.
- What happens if the FAQ/enquiry HTTP request times out or returns an error? A user-friendly error message is shown and the input re-enables; no SSE connection is involved.
- What happens when the backend returns a non-streaming error (e.g., 500)? A user-friendly error banner appears without crashing the UI.
- What happens when the user creates more than 5 conversations in a session? The sidebar retains only the 5 most recent; the oldest is silently dropped. No warning is shown — this is expected behaviour for a session-scoped tool.
- What happens on a very narrow mobile viewport? The sidebar is hidden by default and toggled via a hamburger icon; the input area remains fully usable.
- What happens when the orchestrator returns no trace data? The trace panel shows a "No trace available" placeholder rather than an empty/broken panel.
- What happens if the user presses Enter on an empty input? Submission is blocked and the input shakes or shows a subtle validation hint.

---

## Requirements *(mandatory)*

### Functional Requirements

**Conversational Interface**

- **FR-001**: The UI MUST provide a single primary text input that supports multiline entry (Shift+Enter for newline, Enter to submit).
- **FR-002**: The UI MUST disable the submit action while a response is loading or a provisioning SSE stream is active.
- **FR-003**: The chat area MUST auto-scroll to the latest message when a new message or status update arrives.

**Response Delivery**

- **FR-004a**: For **FAQ and enquiry intents**, the UI MUST submit the request and display a loading indicator while awaiting the complete JSON response. When the response arrives, the full answer is rendered at once. There is no token-by-token streaming for these intents.
- **FR-004b**: For **provisioning intents**, the UI MUST open a Server-Sent Events (SSE) connection to `GET /jobs/{job_id}/stream` after the job is confirmed, and render each job status transition (e.g., `queued → in_progress → succeeded`) as it arrives.
- **FR-005**: The UI MUST display a loading/typing indicator immediately after submission for all intent types, persisting until either the complete response is received (FAQ/enquiry) or the SSE stream reaches a terminal job state (provisioning).
- **FR-006**: SSE connection failures on provisioning status streams MUST trigger automatic silent reconnection up to 3 times (with a brief "reconnecting…" indicator). If all 3 attempts fail, a manual retry button MUST be surfaced; any status updates already rendered MUST be preserved throughout.

**Clarification Loop**

- **FR-006a**: When the backend returns `outcome: clarification_needed`, the UI MUST render an inline clarification card directly below the user's original message in the chat thread. The card MUST display the orchestrator's clarification question and provide a single-line text input with a "Submit answer" button.
- **FR-006b**: Submitting the clarification answer MUST call `POST /requests/{infra_request_id}/clarify` with the answer text, using the `infra_request_id` returned in the original response. The UI MUST then handle the follow-up response using the same intent routing rules (clarification_needed again, or routed outcome).
- **FR-006c**: After 2 failed clarification rounds, the backend returns a rejection. The UI MUST display the rejection message inline and re-enable the input for a fresh query.

**Intent Confirmation**

- **FR-007**: For provisioning intents, the UI MUST display a single intent confirmation card that combines both the orchestrator's plain-language intent restatement AND the full provisioning confirmation summary (resource name, type, region, machine type, etc. as returned by the backend). This card replaces what would otherwise be two separate confirmation steps. A 20-minute countdown timer MUST be visible on the card. Clicking "Looks right, continue" calls `POST /jobs/{job_id}/confirm`. When the countdown reaches zero: the UI MUST first disable the "Looks right, continue" button, then call `POST /jobs/{job_id}/cancel`, then display an expiry message — in that order. Clicking "Rephrase" calls `POST /jobs/{job_id}/cancel` and restores the query to the input.
- **FR-007a**: For enquiry intents, the UI MUST display a lightweight intent confirmation card showing the `intent_summary` string provided by the backend (no parameter summary, no countdown). Clicking "Looks right, continue" renders the enquiry result immediately (the result is already present in the initial response payload — no additional network call is required).
- **FR-007b**: For FAQ intents, the UI MUST NOT show an intent confirmation card. The complete answer MUST be rendered directly when the response arrives.
- **FR-007c**: The intent confirmation card MUST provide a "Rephrase" action that dismisses the card, restores the original query text to the input field, and re-enables the submit button so the user can edit and resubmit. For provisioning intents, "Rephrase" MUST call `POST /jobs/{job_id}/cancel` before dismissing the card.
- **FR-008**: The intent confirmation card MUST be visually distinct from regular message bubbles.

**Conversation History**

- **FR-009**: The UI MUST maintain a list of up to 5 conversations for the current browser session in the left sidebar, ordered with the most recent at the top. When a 6th conversation is created, the oldest is silently removed from the sidebar.
- **FR-009a**: The sidebar header MUST contain a "New Conversation" button that, when clicked, clears the main chat area and begins a new conversation thread. The previous conversation is preserved in the sidebar history (subject to the 5-conversation cap).
- **FR-010**: The user MUST be able to click a past conversation in the sidebar to restore its full message exchange in the main chat area.
- **FR-011**: Each sidebar entry MUST show a short auto-generated title derived from the first user message of that conversation (truncated to fit the sidebar width).

**Agent Execution Trace**

- **FR-012**: The UI MUST provide a collapsible panel (right drawer or inline below the response) that displays the agent invocation sequence with per-agent status (pending / running / completed / failed).
- **FR-013**: For provisioning intents, the trace panel MUST update in real time driven by the provisioning SSE stream. For FAQ and enquiry intents, trace data arrives as part of the complete JSON response and is rendered once when the response is received.
- **FR-013a**: The trace snapshot for each conversation MUST be persisted in the session-scoped Conversation object. When the user revisits a past conversation via the sidebar, the trace panel MUST display the last-captured trace snapshot for that conversation.
- **FR-014**: If execution duration data is present in the trace events, the UI MUST display it alongside the corresponding agent entry.

**Theme**

- **FR-015**: The UI MUST provide a light/dark theme toggle accessible from the main layout at all times.
- **FR-016**: The selected theme MUST be persisted in browser local storage and restored on next visit.
- **FR-017**: Both themes MUST meet WCAG AA contrast ratios for all text and interactive elements.

**Responsive Design**

- **FR-018**: The sidebar MUST collapse and be togglable via a button on viewports narrower than tablet breakpoint.
- **FR-019**: All primary interactions (submit query, view response, toggle theme) MUST be fully operable on mobile screen sizes without horizontal scrolling.

**Identity and Daily Limit**

- **FR-021**: On startup, the UI MUST call `GET /auth/me` and display the `user_id` and `role` in the header.
- **FR-022**: The UI MUST display the user's `daily_provisioning_count` and `daily_provisioning_limit` as a subtle indicator (e.g., "3 / 10 today") in the header, visible at all times. This indicator MUST update after each provisioning request is successfully queued.
- **FR-023**: All requests to the backend MUST include the API key as an `Authorization: Bearer <key>` header. The key is read from the `VITE_API_KEY` build-time environment variable.

**Error States**

- **FR-020**: All backend error outcomes MUST be rendered as inline messages in the chat thread, directly below the user's original message — not as toasts, modals, or banners outside the chat flow.
- **FR-020a**: A `guardrail_violation` (403) MUST display the backend's violation message verbatim (which field was violated and what the allowed values are) with a warning visual style, and suggest the user contact a platform engineer.
- **FR-020b**: A `rate_limited` (429) MUST display the message "Your daily provisioning limit resets at midnight UTC." with a warning visual style and the user's current count shown.
- **FR-020c**: A `rejected` (400) MUST display the backend's rejection message in a neutral style and invite the user to rephrase and try again.
- **FR-020d**: An unreachable backend or unexpected 5xx MUST display a generic "Something went wrong — please try again" message in a neutral style without exposing raw error details. The input MUST re-enable so the user can retry.

### Key Entities

- **Conversation**: A session-scoped container holding an ordered list of messages, identified by a generated title from the first user message. At most 5 conversations are retained per session; the oldest is evicted when a 6th is created.
- **Message**: A single exchange unit with a role (user or assistant), content (text), and optional metadata (timestamp, intent confirmation flag).
- **IntentConfirmation**: A structured payload attached to an assistant message indicating the orchestrator's interpreted intent and confidence level. Contains: `intent_summary` (plain-language string from the backend describing what the orchestrator understood), `intent` (the intent type: provision/enquiry), `confidence`, and for provisioning intents: `job_id`, `confirmation_summary`, and `expires_at`.
- **AgentTraceEntry**: A record representing one agent's execution within a request — includes agent name, role description, status, and optional duration. Persisted in the session-scoped Conversation object so the trace snapshot is available when revisiting a past conversation.
- **StreamEvent**: A real-time SSE event from the `GET /jobs/{job_id}/stream` endpoint carrying a provisioning job status transition (`event: status`) or an end-of-stream signal (`event: done`). SSE is used exclusively for provisioning status — FAQ and enquiry responses arrive as complete JSON, not as stream events.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For provisioning and enquiry intents, the intent confirmation card appears within 2 seconds of query submission. For FAQ intents, the complete answer renders within 5 seconds of submission under normal network conditions. After confirming a provisioning intent, the first SSE job status event arrives within 2 seconds.
- **SC-002**: The interface remains interactive (input accessible, scrollable) while a provisioning SSE stream is active or a FAQ/enquiry response is loading — no full-page blocking or freeze detectable by the user.
- **SC-003**: Users can switch between light and dark themes in one interaction, with the change taking effect immediately across all visible components.
- **SC-004**: On a mobile device (320px minimum width), all core interactions — submit query, read response, toggle sidebar, switch theme — are completable without horizontal scrolling.
- **SC-005**: For provisioning and enquiry intents, the intent confirmation card appears before any result is shown, and the result never renders without an explicit user confirmation click. For FAQ intents, no confirmation card appears and the answer renders directly.
- **SC-006**: The execution trace panel reflects agent state transitions within 1 second of the corresponding backend event arriving.
- **SC-007**: A user can revisit any conversation from the current session via the sidebar within 2 clicks or taps.
- **SC-008**: When the backend returns any error (4xx or 5xx), the user sees a descriptive inline message in the chat thread within 5 seconds and can submit a new query without reloading the page.

---

## Backend Extension Required

The following backend changes are prerequisites for this frontend:

- **`intent_summary` field**: The web backend MUST add an `intent_summary` string field to all non-FAQ `POST /api/v1/requests` responses (provisioning and enquiry). This field contains a plain-language restatement of the orchestrator's understood intent (e.g., "Check the status of compute instance vm-web-01 in us-central1"). The orchestrator or provisioning agent is responsible for generating this string — the frontend displays it verbatim.

---

## Assumptions

- The FastAPI backend's SSE endpoint (`GET /jobs/{job_id}/stream`) streams provisioning job status transitions only. FAQ and enquiry responses are synchronous JSON — no token streaming.
- Conversation history is session-scoped only (stored in browser memory); persistence across page refreshes or browser restarts is out of scope for this iteration.
- The backend requires API key authentication (`Authorization: Bearer <key>`) on every request. The API key is supplied to the frontend via a build-time environment variable (`VITE_API_KEY`) — no login UI is required.
- The frontend calls `GET /auth/me` on startup to obtain `user_id`, `role`, `daily_provisioning_count`, and `daily_provisioning_limit` for display in the header.
- The orchestrator backend handles all agent routing, trace aggregation, and `intent_summary` generation; the frontend is purely a display layer.
- Both `VITE_API_BASE_URL` and `VITE_API_KEY` are configurable at build time via environment variables.
- Rich markdown or code block rendering in responses is out of scope for this iteration; plain text rendering is sufficient.
- File uploads, voice input, and multi-user support are explicitly out of scope.
- The agent list and their roles are dynamic — the frontend renders whatever agent names and descriptions arrive in trace events without a hardcoded registry.
- Accessibility target is WCAG AA for both themes; AAA is not required in this iteration.
