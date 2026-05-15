import { useEffect } from 'react'
import { useCountdown } from '@/hooks/useCountdown'

interface CountdownTimerProps {
  expiresAt: string
  onExpired: () => void
}

export function CountdownTimer({ expiresAt, onExpired }: CountdownTimerProps) {
  const { secondsLeft, isExpired } = useCountdown(expiresAt)

  useEffect(() => {
    if (isExpired) onExpired()
  }, [isExpired, onExpired])

  const minutes = Math.floor(secondsLeft / 60)
  const seconds = secondsLeft % 60
  const display = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  const isUrgent = secondsLeft <= 30

  return (
    <span
      className={`font-mono text-sm tabular-nums ${isUrgent ? 'text-red-500 dark:text-red-400' : 'text-surface-muted'}`}
      aria-live="polite"
      aria-label={`Confirmation expires in ${display}`}
    >
      {display}
    </span>
  )
}
