import { useRef, useState } from 'react'
import type { ClarificationPayload } from '@/types/entities'

interface ClarificationCardProps {
  clarification: ClarificationPayload
  onSubmit: (answer: string) => Promise<void>
}

export function ClarificationCard({ clarification, onSubmit }: ClarificationCardProps) {
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  if (clarification.answered) {
    return (
      <div className="rounded-lg border border-surface-border bg-surface-subtle dark:bg-surface-subtle-dark p-3 text-sm text-surface-muted">
        Answer submitted.
      </div>
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = answer.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    try {
      await onSubmit(trimmed)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-4 space-y-3">
      <p className="text-sm font-medium text-surface-fg dark:text-surface-fg-dark">
        {clarification.question}
      </p>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          disabled={submitting}
          placeholder="Your answer…"
          aria-label="Clarification answer"
          className="flex-1 rounded-md border border-surface-border bg-white dark:bg-surface-dark px-3 py-1.5 text-sm text-surface-fg dark:text-surface-fg-dark placeholder:text-surface-muted focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={submitting || !answer.trim()}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Sending…' : 'Submit answer'}
        </button>
      </form>
    </div>
  )
}
