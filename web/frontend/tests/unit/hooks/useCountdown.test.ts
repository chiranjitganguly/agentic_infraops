import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useCountdown } from '@/hooks/useCountdown'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useCountdown', () => {
  it('returns secondsLeft=0 and isExpired=true when expiresAt is null', () => {
    const { result } = renderHook(() => useCountdown(null))
    expect(result.current.secondsLeft).toBe(0)
    expect(result.current.isExpired).toBe(true)
  })

  it('returns correct initial secondsLeft for a future timestamp', () => {
    const expiresAt = new Date(Date.now() + 90_000).toISOString() // 90 seconds from now
    const { result } = renderHook(() => useCountdown(expiresAt))
    expect(result.current.secondsLeft).toBeGreaterThanOrEqual(89)
    expect(result.current.secondsLeft).toBeLessThanOrEqual(90)
    expect(result.current.isExpired).toBe(false)
  })

  it('decrements each second', () => {
    const expiresAt = new Date(Date.now() + 5_000).toISOString()
    const { result } = renderHook(() => useCountdown(expiresAt))

    act(() => {
      vi.advanceTimersByTime(2_000)
    })

    expect(result.current.secondsLeft).toBeLessThanOrEqual(3)
    expect(result.current.isExpired).toBe(false)
  })

  it('sets isExpired=true when countdown reaches zero', () => {
    const expiresAt = new Date(Date.now() + 2_000).toISOString()
    const { result } = renderHook(() => useCountdown(expiresAt))

    act(() => {
      vi.advanceTimersByTime(3_000)
    })

    expect(result.current.secondsLeft).toBe(0)
    expect(result.current.isExpired).toBe(true)
  })

  it('does not go below 0', () => {
    const expiresAt = new Date(Date.now() - 5_000).toISOString() // already expired
    const { result } = renderHook(() => useCountdown(expiresAt))
    expect(result.current.secondsLeft).toBe(0)
    expect(result.current.isExpired).toBe(true)
  })

  it('clears interval on unmount', () => {
    const clearSpy = vi.spyOn(globalThis, 'clearInterval')
    const expiresAt = new Date(Date.now() + 10_000).toISOString()
    const { unmount } = renderHook(() => useCountdown(expiresAt))
    unmount()
    expect(clearSpy).toHaveBeenCalled()
  })
})
