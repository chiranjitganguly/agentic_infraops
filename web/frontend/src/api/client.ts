import type { ApiError } from '@/types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL

export const TOKEN_KEY = 'infraops_token'

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiError,
  ) {
    super(body.message)
    this.name = 'ApiRequestError'
  }
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`
  const token = getStoredToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const { headers: _h, ...restInit } = init ?? {}
  const response = await fetch(url, {
    ...restInit,
    headers,
  })

  if (!response.ok) {
    let body: ApiError
    try {
      body = (await response.json()) as ApiError
    } catch {
      body = {
        error_code: 'INTERNAL_ERROR',
        message: `HTTP ${response.status}`,
        details: {},
        correlation_id: null,
        timestamp: new Date().toISOString(),
      }
    }
    throw new ApiRequestError(response.status, body)
  }

  return response.json() as Promise<T>
}
