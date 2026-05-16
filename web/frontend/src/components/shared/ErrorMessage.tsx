import type { ErrorPayload } from '@/types/entities'

interface ErrorMessageProps {
  error: ErrorPayload
  dailyCount?: number
}

function messageFor(error: ErrorPayload, dailyCount?: number): string {
  switch (error.error_code) {
    case 'GUARDRAIL_VIOLATION':
      return error.message
    case 'RATE_LIMIT_EXCEEDED':
      return `Your daily provisioning limit resets at midnight UTC.${
        dailyCount !== undefined ? ` (${dailyCount} resources provisioned today)` : ''
      }`
    case 'VALIDATION_ERROR':
      return error.message
    case 'INTERNAL_ERROR':
    case 'NETWORK_ERROR':
      return 'Something went wrong — please try again.'
    default:
      return 'Something went wrong — please try again.'
  }
}

function hintFor(error: ErrorPayload): string | null {
  switch (error.error_code) {
    case 'GUARDRAIL_VIOLATION':
      return 'A platform engineer can run the same request with elevated permissions.'
    case 'VALIDATION_ERROR':
      return 'Try rephrasing your request with more specific details.'
    default:
      return null
  }
}

function isWarning(error: ErrorPayload): boolean {
  return (
    error.error_code === 'GUARDRAIL_VIOLATION' ||
    error.error_code === 'RATE_LIMIT_EXCEEDED'
  )
}

export function ErrorMessage({ error, dailyCount }: ErrorMessageProps) {
  const warning = isWarning(error)
  const hint = hintFor(error)

  return (
    <div
      role="alert"
      className={[
        'rounded-md border px-3 py-2 text-sm',
        warning
          ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300'
          : 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300',
      ].join(' ')}
    >
      <p>{messageFor(error, dailyCount)}</p>
      {hint && (
        <p className="mt-1 text-xs opacity-75">{hint}</p>
      )}
    </div>
  )
}
