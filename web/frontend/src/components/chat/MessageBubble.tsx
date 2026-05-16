import { useState } from 'react'
import type { Message } from '@/types/entities'
import { LoadingIndicator } from '@/components/shared/LoadingIndicator'
import { ErrorMessage } from '@/components/shared/ErrorMessage'

interface MessageBubbleProps {
  message: Message
  confirmationSlot?: React.ReactNode
  clarificationSlot?: React.ReactNode
  sseState?: 'idle' | 'connecting' | 'open' | 'reconnecting' | 'failed' | 'closed'
  onSseRetry?: () => void
}

// ---------------------------------------------------------------------------
// FAQ answer (T030)
// ---------------------------------------------------------------------------

function FaqAnswer({ content, sources }: { content: string; sources?: string[] }) {
  const [sourcesOpen, setSourcesOpen] = useState(false)

  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed text-slate-800 dark:text-slate-200">{content}</p>

      {sources && sources.length > 0 && (
        <div className="border-t border-slate-100 pt-2 dark:border-slate-700">
          <button
            onClick={() => setSourcesOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            aria-expanded={sourcesOpen}
          >
            <svg
              className={`h-3 w-3 transition-transform ${sourcesOpen ? 'rotate-90' : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
            {sourcesOpen ? 'Hide' : 'Show'} sources ({sources.length})
          </button>

          {sourcesOpen && (
            <ul className="mt-1.5 space-y-0.5 pl-4">
              {sources.map((src, i) => (
                <li key={i} className="text-xs text-slate-500 dark:text-slate-400">
                  {src}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Enquiry answer (T031)
// ---------------------------------------------------------------------------

function EnquiryAnswer({ content, enquiry_data }: Pick<Message, 'content' | 'enquiry_data'>) {
  const data = enquiry_data

  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed text-slate-800 dark:text-slate-200">{content}</p>

      {data && (
        <dl className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800/50">
          {data.resource_type && (
            <div className="flex justify-between py-0.5 text-xs">
              <dt className="text-slate-500 dark:text-slate-400">Type</dt>
              <dd className="font-mono text-slate-700 dark:text-slate-300">{data.resource_type}</dd>
            </div>
          )}
          {data.query_type === 'single' ? (
            <>
              {data.resource_name && (
                <div className="flex justify-between py-0.5 text-xs">
                  <dt className="text-slate-500 dark:text-slate-400">Name</dt>
                  <dd className="font-mono text-slate-700 dark:text-slate-300">{data.resource_name}</dd>
                </div>
              )}
              {data.gcp_status && (
                <div className="flex justify-between py-0.5 text-xs">
                  <dt className="text-slate-500 dark:text-slate-400">Status</dt>
                  <dd>
                    <StatusBadge status={data.gcp_status} />
                  </dd>
                </div>
              )}
            </>
          ) : (
            <div className="flex justify-between py-0.5 text-xs">
              <dt className="text-slate-500 dark:text-slate-400">Resources found</dt>
              <dd className="font-mono text-slate-700 dark:text-slate-300">
                {data.total_count ?? data.resources?.length ?? 0}
              </dd>
            </div>
          )}
        </dl>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const isRunning = /running|active|ready/i.test(status)
  const isStopped = /stopped|terminated|deleted/i.test(status)

  return (
    <span
      className={[
        'rounded-full px-1.5 py-0.5 font-mono text-xs font-medium',
        isRunning
          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          : isStopped
          ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
          : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
      ].join(' ')}
    >
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Job status list for provisioning (Phase 4 SSE updates render here)
// ---------------------------------------------------------------------------

function JobStatusList({ message }: { message: Message }) {
  if (message.job_statuses.length === 0 && !message.confirmation) return null

  const statuses = message.job_statuses

  return (
    <div className="space-y-1">
      {statuses.map((update, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <JobStatusIcon status={update.status} />
          <span className="font-mono text-slate-600 dark:text-slate-300">{update.status}</span>
        </div>
      ))}
    </div>
  )
}

function JobStatusIcon({ status }: { status: string }) {
  if (/succeeded|completed/.test(status)) {
    return (
      <svg className="h-3.5 w-3.5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    )
  }
  if (/failed|rollback/.test(status)) {
    return (
      <svg className="h-3.5 w-3.5 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    )
  }
  return (
    <svg className="h-3.5 w-3.5 animate-spin text-blue-500" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
      <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// MessageBubble (T026 — outer shell + routing T030/T031/T032)
// ---------------------------------------------------------------------------

export function MessageBubble({ message, confirmationSlot, clarificationSlot, sseState, onSseRetry }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2.5 text-sm text-white dark:bg-blue-500">
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant / system message
  return (
    <div className="flex justify-start">
      <div className="flex max-w-[85%] flex-col gap-2">
        {/* Loading state */}
        {message.loading && (
          <div className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 dark:bg-slate-800">
            <LoadingIndicator />
          </div>
        )}

        {/* Error state (T032 — all four FR-020a–d variants via ErrorMessage) */}
        {!message.loading && message.error && (
          <ErrorMessage error={message.error} />
        )}

        {/* Clarification card slot (Phase 4) */}
        {!message.loading && !message.error && message.clarification && (
          clarificationSlot ?? (
            <div className="rounded-2xl rounded-bl-sm bg-amber-50 px-4 py-3 text-sm dark:bg-amber-950/30">
              <p className="font-medium text-amber-800 dark:text-amber-300">Clarification needed</p>
              <p className="mt-1 text-amber-700 dark:text-amber-400">{message.clarification.question}</p>
            </div>
          )
        )}

        {/* Intent confirmation card slot (Phase 4) */}
        {!message.loading && !message.error && message.confirmation && !message.confirmation.confirmed && !message.confirmation.cancelled && (
          confirmationSlot ?? (
            <div className="rounded-2xl rounded-bl-sm border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-800 dark:bg-blue-950/20">
              <p className="text-xs font-medium uppercase tracking-wide text-blue-600 dark:text-blue-400">
                Intent understood
              </p>
              {message.confirmation.intent_summary && (
                <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                  {message.confirmation.intent_summary}
                </p>
              )}
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Confirmation UI — coming in Phase 4
              </p>
            </div>
          )
        )}

        {/* FAQ answer (T030) */}
        {!message.loading && !message.error && message.intent === 'faq' && (
          <div className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 dark:bg-slate-800">
            <FaqAnswer content={message.content} sources={message.faq_sources} />
          </div>
        )}

        {/* Enquiry answer (T031) */}
        {!message.loading && !message.error && message.intent === 'enquiry' && (
          <div className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 dark:bg-slate-800">
            <EnquiryAnswer content={message.content} enquiry_data={message.enquiry_data} />
          </div>
        )}

        {/* Provisioning SSE job status list (grows as stream events arrive) */}
        {!message.loading && !message.error && message.intent === 'provision' && message.confirmation?.confirmed && (
          <div className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 dark:bg-slate-800 space-y-2">
            <JobStatusList message={message} />
            {sseState === 'reconnecting' && (
              <p className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
                <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                  <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
                </svg>
                Reconnecting…
              </p>
            )}
            {sseState === 'failed' && (
              <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400" role="alert">
                <span>Status stream lost.</span>
                {onSseRetry && (
                  <button
                    onClick={onSseRetry}
                    className="underline hover:no-underline focus:outline-none focus:ring-1 focus:ring-red-400 rounded"
                  >
                    Retry
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Fallback — plain text content (system messages, unexpected cases) */}
        {!message.loading && !message.error && !message.intent && !message.clarification && !message.confirmation && message.content && (
          <div className="rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-3 dark:bg-slate-800">
            <p className="text-sm leading-relaxed text-slate-800 dark:text-slate-200">{message.content}</p>
          </div>
        )}
      </div>
    </div>
  )
}
