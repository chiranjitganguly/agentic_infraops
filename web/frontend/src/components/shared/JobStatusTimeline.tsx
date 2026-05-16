import { useState } from 'react'
import type { JobStatusUpdate, SseStreamState } from '@/types/entities'

interface JobStatusTimelineProps {
  jobId: string | null
  jobStatuses: JobStatusUpdate[]
  sseState: SseStreamState
  onRetry?: () => void
}

const STEPS = [
  { key: 'queued',      label: 'Queued' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'succeeded',   label: 'Completed' },
] as const

type StepState = 'pending' | 'active' | 'done' | 'failed'

function getStepState(stepKey: string, latestStatus: string | null): StepState {
  if (!latestStatus) return 'pending'

  const isFailed = /failed|rollback|cancelled/.test(latestStatus)
  const order = ['queued', 'in_progress', 'retrying', 'succeeded']
  const stepIdx = order.indexOf(stepKey === 'succeeded' ? 'succeeded' : stepKey)
  const currentIdx = order.indexOf(latestStatus)

  if (isFailed) {
    if (stepKey === 'succeeded') return 'failed'
    if (stepIdx < currentIdx) return 'done'
    if (stepIdx === currentIdx) return 'active'
    return 'pending'
  }

  if (latestStatus === 'succeeded') return 'done'
  if (stepIdx < currentIdx) return 'done'
  if (stepKey === latestStatus || (stepKey === 'in_progress' && latestStatus === 'retrying')) return 'active'
  return 'pending'
}

function StepIcon({ state }: { state: StepState }) {
  if (state === 'done') {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-500 text-white">
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
    )
  }
  if (state === 'failed') {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-white">
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </span>
    )
  }
  if (state === 'active') {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-500">
        <svg className="h-3.5 w-3.5 animate-spin text-white" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
          <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
        </svg>
      </span>
    )
  }
  return (
    <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800" />
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={handleCopy}
      title="Copy job ID"
      className="ml-1 rounded p-0.5 text-green-600 hover:bg-green-100 dark:text-green-400 dark:hover:bg-green-900/30 transition-colors"
    >
      {copied ? (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  )
}

export function JobStatusTimeline({ jobId, jobStatuses, sseState, onRetry }: JobStatusTimelineProps) {
  const latestStatus = jobStatuses.length > 0 ? jobStatuses[jobStatuses.length - 1].status : null
  const isFailed = latestStatus !== null && /failed|rollback|cancelled/.test(latestStatus)
  const isSucceeded = latestStatus === 'succeeded'

  return (
    <div className="space-y-3">
      {/* Job submitted acknowledgement banner */}
      {jobId && (
        <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2.5 dark:border-green-800 dark:bg-green-950/30">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <svg className="h-4 w-4 shrink-0 text-green-600 dark:text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <path d="M22 2L11 13" /><path d="M22 2L15 22 11 13 2 9l20-7z" />
              </svg>
              <p className="text-sm font-semibold text-green-700 dark:text-green-400">
                Job submitted
              </p>
            </div>
            <div className="flex items-center gap-1">
              <span className="font-mono text-xs text-green-700 dark:text-green-400 select-all">
                {jobId}
              </span>
              <CopyButton text={jobId} />
            </div>
          </div>
          <p className="mt-1 text-xs text-green-600 dark:text-green-500">
            Use this Job ID to track progress at any time.
          </p>
        </div>
      )}

      {/* Section label */}
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Provisioning Status
      </p>

      {/* Timeline steps */}
      <ol className="relative space-y-0" aria-label="Provisioning progress">
        {STEPS.map((step, idx) => {
          const state = getStepState(step.key, latestStatus)
          const isLast = idx === STEPS.length - 1
          return (
            <li key={step.key} className="flex gap-3">
              <div className="flex flex-col items-center">
                <StepIcon state={state} />
                {!isLast && (
                  <div
                    className={[
                      'mt-1 w-0.5 flex-1 min-h-[1.5rem]',
                      state === 'done' ? 'bg-green-400' : 'bg-slate-200 dark:bg-slate-700',
                    ].join(' ')}
                  />
                )}
              </div>
              <div className="pb-4 pt-0.5">
                <p
                  className={[
                    'text-sm font-medium',
                    state === 'active' ? 'text-blue-600 dark:text-blue-400' :
                    state === 'done'   ? 'text-green-700 dark:text-green-400' :
                    state === 'failed' ? 'text-red-600 dark:text-red-400' :
                    'text-slate-400 dark:text-slate-500',
                  ].join(' ')}
                >
                  {step.label}
                  {state === 'active' && (
                    <span className="ml-2 text-xs font-normal text-slate-500 dark:text-slate-400">
                      {latestStatus === 'retrying' ? '(retrying…)' : 'in progress…'}
                    </span>
                  )}
                </p>
              </div>
            </li>
          )
        })}
      </ol>

      {/* Final state banners */}
      {isSucceeded && (
        <div className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-950/30 dark:text-green-400">
          Resource provisioned successfully.
        </div>
      )}
      {isFailed && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
          Provisioning {latestStatus}. Check logs for details.
        </div>
      )}

      {/* SSE connection states */}
      {sseState === 'connecting' && !latestStatus && (
        <p className="flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500" aria-live="polite">
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
          </svg>
          Connecting to status stream…
        </p>
      )}
      {sseState === 'reconnecting' && (
        <p className="flex items-center gap-1.5 text-xs text-amber-500" aria-live="polite">
          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
          </svg>
          Reconnecting…
        </p>
      )}
      {sseState === 'failed' && (
        <div className="flex items-center gap-2 text-xs text-red-500" role="alert">
          <span>Status stream unavailable.</span>
          {onRetry && (
            <button onClick={onRetry} className="underline hover:no-underline focus:outline-none">
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  )
}
