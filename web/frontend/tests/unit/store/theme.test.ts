import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// Replace persist with a pass-through so we can test store logic
// without depending on localStorage being available in the test runner.
vi.mock('zustand/middleware', async (importOriginal) => {
  const actual = await importOriginal<typeof import('zustand/middleware')>()
  return {
    ...actual,
    // Strip persistence — return state fn unwrapped so we get a plain store.
    persist: (fn: Parameters<typeof actual.persist>[0]) => fn,
  }
})

// Import AFTER the mock is wired.
import { useThemeStore } from '@/store/theme'

function resetStore() {
  document.documentElement.classList.remove('dark')
  useThemeStore.setState({ theme: 'light' })
}

describe('theme store', () => {
  beforeEach(resetStore)
  afterEach(resetStore)

  // -------------------------------------------------------------------------
  // State transitions
  // -------------------------------------------------------------------------

  it('starts in light mode by default', () => {
    expect(useThemeStore.getState().theme).toBe('light')
  })

  it('toggleTheme switches light → dark', () => {
    useThemeStore.getState().toggleTheme()
    expect(useThemeStore.getState().theme).toBe('dark')
  })

  it('toggleTheme switches dark → light', () => {
    useThemeStore.setState({ theme: 'dark' })
    useThemeStore.getState().toggleTheme()
    expect(useThemeStore.getState().theme).toBe('light')
  })

  it('toggleTheme is idempotent over two calls', () => {
    useThemeStore.getState().toggleTheme() // → dark
    useThemeStore.getState().toggleTheme() // → light
    expect(useThemeStore.getState().theme).toBe('light')
  })

  it('setTheme("dark") sets state to dark', () => {
    useThemeStore.getState().setTheme('dark')
    expect(useThemeStore.getState().theme).toBe('dark')
  })

  it('setTheme("light") sets state to light', () => {
    useThemeStore.setState({ theme: 'dark' })
    useThemeStore.getState().setTheme('light')
    expect(useThemeStore.getState().theme).toBe('light')
  })

  // -------------------------------------------------------------------------
  // DOM class side-effect
  // -------------------------------------------------------------------------

  it('adds "dark" class to documentElement when switching to dark', () => {
    useThemeStore.getState().toggleTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('removes "dark" class from documentElement when switching to light', () => {
    document.documentElement.classList.add('dark')
    useThemeStore.setState({ theme: 'dark' })
    useThemeStore.getState().toggleTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('setTheme("dark") adds dark class synchronously', () => {
    useThemeStore.getState().setTheme('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('setTheme("light") removes dark class synchronously', () => {
    document.documentElement.classList.add('dark')
    useThemeStore.getState().setTheme('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
