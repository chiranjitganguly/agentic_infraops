import type { AgentTraceEntry as AgentTraceEntryType } from '@/types/entities'

const STATUS_STYLES: Record<AgentTraceEntryType['status'], string> = {
  pending:   'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  running:   'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  completed: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  failed:    'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
}

const STATUS_ICONS: Record<AgentTraceEntryType['status'], string> = {
  pending:   '○',
  running:   '◌',
  completed: '✓',
  failed:    '✕',
}

interface AgentTraceEntryProps {
  entry: AgentTraceEntryType
}

export function AgentTraceEntry({ entry }: AgentTraceEntryProps) {
  return (
    <li className="flex items-start gap-3 py-1.5">
      <span
        className={`mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-xs font-bold ${STATUS_STYLES[entry.status]}`}
        aria-label={entry.status}
      >
        {STATUS_ICONS[entry.status]}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium text-surface-fg dark:text-surface-fg-dark truncate">
            {entry.agent_name}
          </span>
          {entry.role && (
            <span className="text-xs text-surface-muted truncate">
              {entry.role}
            </span>
          )}
        </div>
        {entry.duration_ms !== null && entry.duration_ms !== undefined && (
          <span className="text-xs text-surface-muted">
            {entry.duration_ms < 1000
              ? `${entry.duration_ms}ms`
              : `${(entry.duration_ms / 1000).toFixed(1)}s`}
          </span>
        )}
      </div>

      <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${STATUS_STYLES[entry.status]}`}>
        {entry.status}
      </span>
    </li>
  )
}
