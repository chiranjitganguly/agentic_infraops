import { apiFetch } from './client'
import type { GetMeResponse } from '@/types/api'

export interface LoginResponse {
  token: string
  user_id: string
  role: string
}

export function getMe(): Promise<GetMeResponse> {
  return apiFetch<GetMeResponse>('/auth/me')
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}
