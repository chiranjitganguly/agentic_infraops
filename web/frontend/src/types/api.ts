/**
 * API contract types for the Infra Q&A UI frontend.
 *
 * These types mirror the FastAPI backend response shapes confirmed in research.md.
 * All fields are as emitted by the backend — do not add client-side defaults here.
 *
 * Backend source: web/backend/routers/{requests,jobs,auth,sse}.py
 */

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

export interface ApiError {
  error_code:
    | 'GUARDRAIL_VIOLATION'
    | 'RATE_LIMIT_EXCEEDED'
    | 'VALIDATION_ERROR'
    | 'INTERNAL_ERROR'
    | 'JOB_NOT_CANCELLABLE'
    | 'IDEMPOTENCY_CONFLICT'
  message: string
  details: Record<string, unknown>
  correlation_id: string | null
  timestamp: string // ISO-8601
}

// ---------------------------------------------------------------------------
// POST /api/v1/requests
// ---------------------------------------------------------------------------

export interface SubmitRequestBody {
  raw_input: string
  channel?: 'web' // always 'web' from the browser
}

// Backend extension required — absent until deployed; frontend degrades gracefully
export interface TraceEntry {
  agent_name: string
  role: string | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  duration_ms: number | null
}

/** HTTP 200 — clarification needed before routing */
export interface ClarificationNeededResponse {
  infra_request_id: string
  status: 'clarification_needed'
  clarification_question: string
  correlation_id: string
  clarification_round?: number // present on /clarify follow-up (1 or 2)
  trace?: TraceEntry[]
}

/** HTTP 202/200 — provisioning intent routed */
export interface ProvisioningRoutedResponse {
  infra_request_id: string
  job_id: string
  intent: 'provision'
  status: 'awaiting_confirmation' | 'queued' | 'in_progress' | 'completed' | 'failed'
  confirmation_summary: string | null // human-readable summary; null when job already active
  expires_at: string | null // ISO-8601; null when job already active
  intent_summary?: string | null
  correlation_id: string
  trace?: TraceEntry[]
}

/** HTTP 200 — enquiry intent answered */
export interface EnquiryRoutedResponse {
  infra_request_id: string
  intent: 'enquiry'
  query_type: 'single' | 'list'
  status: 'answered'
  answer: string
  queried_at: string // ISO-8601
  correlation_id: string
  resource_type: string
  // single query:
  resource_name?: string
  gcp_status?: string
  metadata?: Record<string, unknown>
  // list query:
  resources?: unknown[]
  total_count?: number
  // Backend extension required — absent until deployed:
  intent_summary?: string
  trace?: TraceEntry[]
}

/** HTTP 200 — FAQ intent answered */
export interface FaqRoutedResponse {
  infra_request_id: string
  intent: 'faq'
  status: 'answered'
  answer: string
  sources: string[]
  correlation_id: string
  trace?: TraceEntry[]
}

export type SubmitRequestResponse =
  | ClarificationNeededResponse
  | ProvisioningRoutedResponse
  | EnquiryRoutedResponse
  | FaqRoutedResponse

// ---------------------------------------------------------------------------
// POST /api/v1/requests/{infra_request_id}/clarify
// ---------------------------------------------------------------------------

export interface ClarifyBody {
  clarification: string
}

// Response is the same union as SubmitRequestResponse

// ---------------------------------------------------------------------------
// POST /api/v1/jobs/{job_id}/confirm
// ---------------------------------------------------------------------------

export interface ConfirmJobResponse {
  job_id: string
  status: 'queued'
  message: string
  correlation_id: string
}

// ---------------------------------------------------------------------------
// POST /api/v1/jobs/{job_id}/cancel
// ---------------------------------------------------------------------------

export interface CancelJobResponse {
  job_id: string
  status: 'cancelled'
  correlation_id: string
}

// ---------------------------------------------------------------------------
// GET /api/v1/jobs/{job_id}
// ---------------------------------------------------------------------------

export interface GetJobResponse {
  job_id: string
  resource_type: string
  resource_name: string
  region: string
  status: JobStatus
  retry_count: number
  gcp_resource_id: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  correlation_id: string
}

// ---------------------------------------------------------------------------
// GET /api/v1/jobs/{job_id}/stream  — SSE event payloads
// ---------------------------------------------------------------------------

export interface SseStatusEventData {
  job_id: string
  status: JobStatus
  // Backend extension required — trace snapshot carried on status events:
  trace?: TraceEntry[]
}

// event: 'status' → data: SseStatusEventData (JSON-parsed)
// event: 'done'   → data: '' (stream terminal)

export type JobStatus =
  | 'awaiting_confirmation'
  | 'queued'
  | 'in_progress'
  | 'retrying'
  | 'rollback'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set([
  'succeeded',
  'failed',
  'cancelled',
])

// ---------------------------------------------------------------------------
// GET /api/v1/auth/me
// ---------------------------------------------------------------------------

export interface GetMeResponse {
  user_id: string
  role: 'developer' | 'platform_engineer'
  api_key_expires_at: string | null // ISO-8601
  daily_provisioning_count: number
  daily_provisioning_limit: number
}
