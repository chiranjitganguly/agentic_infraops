# Implementation Plan: Infra Q&A UI – ReactJS Frontend

**Branch**: `002-infraqa-react-ui` | **Date**: 2026-05-15 | **Spec**: [spec.md](spec.md)  
**Input**: `specs/002-infraqa-react-ui/spec.md`

---

## Summary

Build a ReactJS + TypeScript single-page application that provides a conversational interface to the existing FastAPI web backend (`http://localhost:8000/api/v1`). The frontend connects via synchronous JSON for FAQ/enquiry intents, via SSE (`GET /jobs/{job_id}/stream`) for provisioning job status, and handles the intent confirmation card, clarification loop, and agent trace panel as defined in the spec. State lives in browser memory (session-scoped). The app is served via nginx in Docker.

---

## Technical Context

**Language/Version**: TypeScript 5.x, React 18, Node 20 LTS (build)  
**Primary Dependencies**: Vite (build), React 18 (UI), TailwindCSS v3 (styling), Zustand (state management), `@tanstack/react-query` (data fetching), native `EventSource` API (SSE)  
**Storage**: Browser `localStorage` (theme preference only); browser memory for session-scoped conversation history  
**Testing**: Vitest + React Testing Library (unit/component), Playwright (E2E smoke)  
**Target Platform**: Browser (Chrome 118+, Firefox 119+, Safari 17+); served via nginx Docker container  
**Project Type**: Single-page web application  
**Performance Goals**: First Contentful Paint < 2s on 4G; SSE first status event rendered < 1s after arrival (SC-006)  
**Constraints**: Must run in Docker Compose alongside existing backend; no backend changes required except `intent_summary` field addition (spec: Backend Extension Required)  
**Scale/Scope**: Single-user per session; session-scoped history (5 conversations max)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I — Agent-First Design | ✅ Pass | Frontend is a display layer; all agent logic stays in backend |
| II — Infrastructure-as-Code | ✅ Pass | Dockerfile + docker-compose service required (see Phase 1) |
| III — Observability-First | ✅ Pass | Browser console structured errors acceptable for UI layer; no server-side observability emitted by the frontend |
| IV — Safety & Guardrails | ✅ Pass | No infrastructure mutation from frontend; all guardrails enforced in backend |
| V — Idempotency & Resilience | ✅ Pass | SSE reconnect logic (3 attempts); countdown expiry calls cancel explicitly |
| VI — Contract-First | ✅ Pass | TypeScript API contracts generated in Phase 1 before component implementation |
| X — Approved Technology Standards | ⚠️ Justified Exception | React/TypeScript is not in the Python-centric approved list. Justified: the constitution's technology standards target backend agents/business_logic/DAGs. The web UI layer is a new concern — ReactJS is the spec-mandated choice reviewed during speckit-clarify. No architectural review override needed. |
| XIV — Testing Standards | ✅ Pass | Vitest unit tests + Playwright smoke test required |
| XV — Containerization | ✅ Pass | Nginx Dockerfile + docker-compose service required |

**No blocking violations.** One justified exception (Principle X) documented above.

---

## Project Structure

### Documentation (this feature)

```text
specs/002-infraqa-react-ui/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/           ← Phase 1 output
│   ├── api.ts           ← API request/response types (TypeScript)
│   └── entities.ts      ← Frontend entity types (Conversation, Message, etc.)
└── tasks.md             ← Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
web/frontend/
├── Dockerfile                    ← nginx multi-stage build
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── env.d.ts                  ← VITE_API_KEY, VITE_API_BASE_URL types
│   ├── api/
│   │   ├── client.ts             ← fetch wrapper with Authorization header
│   │   ├── requests.ts           ← POST /requests, POST /requests/:id/clarify
│   │   ├── jobs.ts               ← POST /jobs/:id/confirm, POST /jobs/:id/cancel, GET /jobs/:id
│   │   ├── auth.ts               ← GET /auth/me
│   │   └── sse.ts                ← EventSource wrapper for GET /jobs/:id/stream
│   ├── store/
│   │   ├── conversations.ts      ← Zustand store: conversation list, active id, 5-cap eviction
│   │   ├── user.ts               ← Zustand store: user_id, role, daily counts
│   │   └── theme.ts              ← Zustand store: light/dark + localStorage persistence
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── Header.tsx
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   └── InputComposer.tsx
│   │   ├── cards/
│   │   │   ├── IntentConfirmationCard.tsx    ← provisioning variant (merged card)
│   │   │   ├── EnquiryConfirmationCard.tsx   ← enquiry variant (lightweight)
│   │   │   └── ClarificationCard.tsx         ← inline clarification question
│   │   ├── trace/
│   │   │   ├── TracePanel.tsx
│   │   │   └── AgentTraceEntry.tsx
│   │   └── shared/
│   │       ├── LoadingIndicator.tsx
│   │       ├── ThemeToggle.tsx
│   │       ├── CountdownTimer.tsx
│   │       └── ErrorMessage.tsx
│   ├── hooks/
│   │   ├── useSubmitRequest.ts   ← POST /requests, route by intent
│   │   ├── useJobStream.ts       ← SSE lifecycle, 3-attempt reconnect
│   │   ├── useCountdown.ts       ← 20-min countdown, expiry callback
│   │   └── useAuth.ts            ← GET /auth/me on mount
│   └── types/
│       ├── api.ts                ← mirrors contracts/api.ts (TS)
│       └── entities.ts           ← mirrors contracts/entities.ts (TS)
└── tests/
    ├── unit/
    │   ├── store/
    │   └── hooks/
    ├── components/
    └── e2e/
        └── smoke.spec.ts
```

**Structure Decision**: Option 2 (web application) — frontend lives at `web/frontend/` alongside the existing `web/backend/`. No monorepo tooling; independent `package.json`. Docker multi-stage build (Node build stage → nginx runtime stage).

---

## Complexity Tracking

No constitution violations requiring justification. The Principle X exception is a scope clarification (UI layer was not covered by the backend-centric standard), not a complexity addition.
