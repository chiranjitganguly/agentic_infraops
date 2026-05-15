import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { AgentTraceEntry } from './AgentTraceEntry'
import type { AgentTraceEntry as AgentTraceEntryType } from '@/types/entities'

interface TracePanelProps {
  trace: AgentTraceEntryType[]
}

export function TracePanel({ trace }: TracePanelProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-2 rounded-md border border-surface-border bg-surface-subtle dark:bg-surface-subtle-dark text-xs">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-medium text-surface-muted hover:text-surface-fg dark:hover:text-surface-fg-dark transition-colors"
        aria-expanded={open}
        aria-controls="trace-panel-list"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
        )}
        Agent trace
        {trace.length > 0 && (
          <span className="ml-auto text-surface-muted">
            {trace.length} {trace.length === 1 ? 'step' : 'steps'}
          </span>
        )}
      </button>

      {open && (
        <div
          id="trace-panel-list"
          className="border-t border-surface-border px-3 pb-2"
        >
          {trace.length === 0 ? (
            <p className="py-3 text-center text-surface-muted">
              No trace available
            </p>
          ) : (
            <ul className="divide-y divide-surface-border" aria-label="Agent execution trace">
              {trace.map((entry, idx) => (
                <AgentTraceEntry key={`${entry.agent_name}-${idx}`} entry={entry} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
