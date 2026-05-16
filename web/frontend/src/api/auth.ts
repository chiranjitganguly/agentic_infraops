import { apiFetch } from './client'
import type { GetMeResponse } from '@/types/api'

export function getMe(): Promise<GetMeResponse> {
  return apiFetch<GetMeResponse>('/auth/me')
}
