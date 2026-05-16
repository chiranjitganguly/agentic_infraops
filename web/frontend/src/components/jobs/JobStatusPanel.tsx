import { useState } from 'react'
import { getJob } from '@/api/jobs'
import { ApiRequestError } from '@/api/client'
import type { GetJobResponse } from '@/types/api'

const STATUS_COLORS: Record<string, string> = {
  awaiting_confirmation: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  queued:     'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  in_progress:'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  retrying:   'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  succeeded:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  failed:     'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  cancelled:  'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
  rollback:   'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
}

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm border-b border-slate-100 dark:border-slate-700 last:border-0">
      <dt className="text-slate-500 dark:text-slate-400 shrink-0">{label}</dt>
      <dd className="font-mono text-slate-800 dark:text-slate-200 text-right break-all">{value}</dd>
    </div>
  )
}

function formatDate(iso: string | null | undefined): string | undefined {
  if (!iso) return undefined
  return new Date(iso).toLocaleString()
}

export function JobStatusPanel() {
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GetJobResponse | null>(null)

  const handleSearch = async () => {
    const jobId = inputValue.trim()
    if (!jobId) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await getJob(jobId)
      setResult(data)
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        setError('No job found with that ID, or you don\'t have access to it.')
      } else {
        setError('Could not retrieve job status. Check the ID and try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-5">
      <div>
        <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
          Job Status Lookup
        </h2>
        <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
          Enter a Job ID to check its current provisioning status.
        </p>
      </div>

      {/* Search bar */}
      <div className="flex gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !loading && handleSearch()}
          placeholder="e.g. bcecb883-f46a-410e-b6f8-f25688623059"
          className={[
            'flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-mono',
            'text-slate-900 placeholder-slate-400 outline-none transition',
            'focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
            'dark:border-slate-600 dark:bg-slate-800 dark:text-slate-50 dark:placeholder-slate-500',
            'dark:focus:border-blue-400 dark:focus:ring-blue-400',
          ].join(' ')}
        />
        <button
          onClick={handleSearch}
          disabled={loading || !inputValue.trim()}
          className={[
            'rounded-lg px-4 py-2 text-sm font-medium transition',
            'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800',
            'disabled:cursor-not-allowed disabled:opacity-40',
            'dark:bg-blue-500 dark:hover:bg-blue-600',
          ].join(' ')}
        >
          {loading ? (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
              <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" className="opacity-75" />
            </svg>
          ) : 'Search'}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400" role="alert">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
          {/* Header */}
          <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-700">
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {result.resource_name}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {result.resource_type.replace(/_/g, ' ')} · {result.region}
              </p>
            </div>
            <StatusBadge status={result.status} />
          </div>

          {/* Details */}
          <dl className="px-4 py-2">
            <DetailRow label="Job ID"       value={result.job_id} />
            <DetailRow label="Region"       value={result.region} />
            <DetailRow label="GCP Resource" value={result.gcp_resource_id} />
            <DetailRow label="Created"      value={formatDate(result.created_at)} />
            <DetailRow label="Updated"      value={formatDate(result.updated_at)} />
            <DetailRow label="Completed"    value={formatDate(result.completed_at)} />
            {result.retry_count > 0 && (
              <DetailRow label="Retries" value={String(result.retry_count)} />
            )}
            {result.error_message && (
              <DetailRow label="Error" value={result.error_message} />
            )}
          </dl>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && !result && (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-slate-400 dark:text-slate-500">
          <svg className="h-10 w-10 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <p className="text-sm">Enter a Job ID above to look up its status.</p>
        </div>
      )}
    </div>
  )
}
