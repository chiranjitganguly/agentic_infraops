import type { IntentConfirmation } from '@/types/entities'

interface EnquiryConfirmationCardProps {
  confirmation: IntentConfirmation
  onConfirm: () => void
  onRephrase: () => void
}

export function EnquiryConfirmationCard({
  confirmation,
  onConfirm,
  onRephrase,
}: EnquiryConfirmationCardProps) {
  if (confirmation.cancelled || confirmation.confirmed) {
    return null
  }

  return (
    <div className="rounded-lg border border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950 p-4 space-y-3">
      {confirmation.intent_summary && (
        <p className="text-sm text-surface-fg dark:text-surface-fg-dark">
          {confirmation.intent_summary}
        </p>
      )}

      <div className="flex gap-2">
        <button
          onClick={onConfirm}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          Looks right, continue
        </button>
        <button
          onClick={onRephrase}
          className="rounded-md border border-surface-border px-3 py-1.5 text-sm font-medium text-surface-fg dark:text-surface-fg-dark hover:bg-surface-hover transition-colors"
        >
          Rephrase
        </button>
      </div>
    </div>
  )
}
