import { useState, useEffect, useRef } from 'react'

interface CountdownResult {
  secondsLeft: number
  isExpired: boolean
}

export function useCountdown(expiresAt: string | null): CountdownResult {
  const [secondsLeft, setSecondsLeft] = useState<number>(() => {
    if (!expiresAt) return 0
    return Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000))
  })

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!expiresAt) return

    const tick = () => {
      const remaining = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000))
      setSecondsLeft(remaining)
      if (remaining === 0 && intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    intervalRef.current = setInterval(tick, 1000)
    tick() // Run immediately to sync with wall clock.

    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current)
    }
  }, [expiresAt])

  return { secondsLeft, isExpired: secondsLeft === 0 }
}
