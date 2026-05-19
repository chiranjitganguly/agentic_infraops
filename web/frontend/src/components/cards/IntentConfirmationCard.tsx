import { useCallback, useState } from 'react'
import { CountdownTimer } from '@/components/shared/CountdownTimer'
import type { IntentConfirmation } from '@/types/entities'

interface IntentConfirmationCardProps {
  confirmation: IntentConfirmation
  onConfirm: () => Promise<void>
  onRephrase: () => void
  onExpired: () => void
}

export function IntentConfirmationCard({
  confirmation,
  onConfirm,
  onRephrase,
  onExpired,
}: IntentConfirmationCardProps) {
  const [confirming, setConfirming] = useState(false)
  const [expired, setExpired] = useState(false)

  const isDisabled = confirming || expired || confirmation.confirmed || confirmation.cancelled

  const handleExpired = useCallback(() => {
    setExpired(true)
    onExpired()
  }, [onExpired])

  const handleConfirm = async () => {
    if (isDisabled) return
    setConfirming(true)
    try {
      await onConfirm()
    } finally {
      setConfirming(false)
    }
  }

  if (confirmation.cancelled) {
    return null
  }

  if (expired && !confirmation.confirmed) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950 p-4 text-sm text-amber-800 dark:text-amber-300">
        Confirmation window expired. Please rephrase your request to try again.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950 p-4 space-y-3">
      {confirmation.intent_summary && (
        <p className="text-sm text-surface-fg dark:text-surface-fg-dark">
          {confirmation.intent_summary}
        </p>
      )}

      {confirmation.confirmation_summary && (
        <pre className="whitespace-pre-wrap rounded-md bg-white/60 px-3 py-2 text-xs leading-relaxed text-slate-700 dark:bg-slate-900/40 dark:text-slate-300">
          {confirmation.confirmation_summary}
        </pre>
      )}

      <div className="flex items-center justify-between gap-3 pt-1">
        <div className="flex gap-2">
          <button
            onClick={handleConfirm}
            disabled={isDisabled}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {confirming ? 'Confirming…' : 'Looks right, continue'}
          </button>
          <button
            onClick={onRephrase}
            disabled={isDisabled}
            className="rounded-md border border-surface-border px-3 py-1.5 text-sm font-medium text-surface-fg dark:text-surface-fg-dark hover:bg-surface-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Rephrase
          </button>
        </div>

        {confirmation.expires_at && !expired && (
          <CountdownTimer
            expiresAt={confirmation.expires_at}
            onExpired={handleExpired}
          />
        )}
      </div>
    </div>
  )
}
