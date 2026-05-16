/**
 * Frontend entity types for the Infra Q&A UI.
 *
 * These are client-side domain objects held in the Zustand store.
 * They are NOT API response shapes — see types/api.ts for those.
 * Defined from data-model.md.
 */

import type { JobStatus } from './api'

// ---------------------------------------------------------------------------
// Core entities
// ---------------------------------------------------------------------------

export interface Conversation {
  id: string
  title: string
  created_at: Date
  messages: Message[]
  trace: AgentTraceEntry[]
  active_job_id: string | null
}

export type MessageRole = 'user' | 'assistant' | 'system'
export type IntentType = 'provision' | 'enquiry' | 'faq'

export interface EnquiryResponseData {
  query_type: 'single' | 'list'
  resource_type?: string
  resource_name?: string
  gcp_status?: string
  metadata?: Record<string, unknown>
  resources?: unknown[]
  total_count?: number
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  created_at: Date
  intent: IntentType | null
  infra_request_id: string | null
  confirmation: IntentConfirmation | null
  clarification: ClarificationPayload | null
  error: ErrorPayload | null
  job_statuses: JobStatusUpdate[]
  loading: boolean
  // FAQ-specific
  faq_sources?: string[]
  // Enquiry-specific
  enquiry_data?: EnquiryResponseData
}

// ---------------------------------------------------------------------------
// Intent confirmation (provisioning + enquiry)
// ---------------------------------------------------------------------------

export interface IntentConfirmation {
  intent_summary: string | null
  intent: 'provision' | 'enquiry'
  confidence: number | null
  // provisioning only:
  job_id: string | null
  confirmation_summary: Record<string, unknown> | null
  expires_at: string | null // ISO-8601
  // state:
  confirmed: boolean
  cancelled: boolean
}

// ---------------------------------------------------------------------------
// Clarification loop
// ---------------------------------------------------------------------------

export interface ClarificationPayload {
  infra_request_id: string
  question: string
  round: number // 1 or 2
  answered: boolean
}

// ---------------------------------------------------------------------------
// Agent trace
// ---------------------------------------------------------------------------

export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface AgentTraceEntry {
  agent_name: string
  role: string | null
  status: AgentStatus
  duration_ms: number | null
}

// ---------------------------------------------------------------------------
// SSE status accumulation
// ---------------------------------------------------------------------------

export interface JobStatusUpdate {
  job_id: string
  status: JobStatus
  received_at: Date
}

// ---------------------------------------------------------------------------
// Error payload (inline chat errors)
// ---------------------------------------------------------------------------

export type ErrorCode =
  | 'GUARDRAIL_VIOLATION'
  | 'RATE_LIMIT_EXCEEDED'
  | 'VALIDATION_ERROR'
  | 'INTERNAL_ERROR'
  | 'NETWORK_ERROR'

export interface ErrorPayload {
  error_code: ErrorCode
  message: string
  http_status: number
}

// ---------------------------------------------------------------------------
// User identity (from GET /auth/me)
// ---------------------------------------------------------------------------

export type UserRole = 'developer' | 'platform_engineer'

export interface UserState {
  user_id: string | null
  role: UserRole | null
  daily_provisioning_count: number
  daily_provisioning_limit: number
  loaded: boolean
}

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

export type Theme = 'light' | 'dark'

// ---------------------------------------------------------------------------
// SSE stream state (hook-level, not persisted)
// ---------------------------------------------------------------------------

export type SseStreamState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'failed'
  | 'closed'
