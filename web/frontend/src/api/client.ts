import type { ApiError } from '@/types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL
const API_KEY = import.meta.env.VITE_API_KEY

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiError,
  ) {
    super(body.message)
    this.name = 'ApiRequestError'
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${API_KEY}`,
      ...init?.headers,
    },
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
