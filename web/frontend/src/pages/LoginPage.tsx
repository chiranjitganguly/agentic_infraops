import { useState, useRef, useEffect } from 'react'
import { login } from '@/api/auth'
import { setStoredToken } from '@/api/client'
import { useUserStore } from '@/store/user'
import type { GetMeResponse } from '@/types/api'
import type { UserRole } from '@/types/entities'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const emailRef = useRef<HTMLInputElement>(null)
  const setUser = useUserStore((s) => s.setUser)

  useEffect(() => {
    emailRef.current?.focus()
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = await login(email.trim().toLowerCase(), password)
      setStoredToken(result.token)
      const mePayload: GetMeResponse = {
        user_id: result.user_id,
        role: result.role as UserRole,
        api_key_expires_at: null,
        daily_provisioning_count: 0,
        daily_provisioning_limit: 10,
      }
      setUser(mePayload)
    } catch {
      setError('Invalid email or password. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 dark:bg-slate-900">
      <div className="w-full max-w-sm">
        {/* Logo / title */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600">
            <svg className="h-7 w-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-50">InfraOps Q&amp;A</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Sign in to your account</p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-slate-200 bg-white px-6 py-8 shadow-sm dark:border-slate-700 dark:bg-slate-800">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
              >
                Email
              </label>
              <input
                ref={emailRef}
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className={[
                  'w-full rounded-lg border px-3 py-2 text-sm',
                  'bg-white text-slate-900 placeholder-slate-400',
                  'dark:bg-slate-900 dark:text-slate-50 dark:placeholder-slate-500',
                  'focus:outline-none focus:ring-2 focus:ring-blue-500',
                  error
                    ? 'border-red-400 dark:border-red-500'
                    : 'border-slate-300 dark:border-slate-600',
                ].join(' ')}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className={[
                  'w-full rounded-lg border px-3 py-2 text-sm',
                  'bg-white text-slate-900 placeholder-slate-400',
                  'dark:bg-slate-900 dark:text-slate-50 dark:placeholder-slate-500',
                  'focus:outline-none focus:ring-2 focus:ring-blue-500',
                  error
                    ? 'border-red-400 dark:border-red-500'
                    : 'border-slate-300 dark:border-slate-600',
                ].join(' ')}
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !email || !password}
              className={[
                'w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-colors',
                loading || !email || !password
                  ? 'cursor-not-allowed bg-blue-400 dark:bg-blue-700'
                  : 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800',
              ].join(' ')}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        {/* Hint */}
        <p className="mt-4 text-center text-xs text-slate-400 dark:text-slate-500">
          Use your InfraOps credentials to sign in.
        </p>
      </div>
    </div>
  )
}
