import { apiFetch } from './client'
import type { ConfirmJobResponse, CancelJobResponse } from '@/types/api'

export function confirmJob(jobId: string): Promise<ConfirmJobResponse> {
  return apiFetch<ConfirmJobResponse>(`/jobs/${jobId}/confirm`, {
    method: 'POST',
  })
}

export function cancelJob(jobId: string): Promise<CancelJobResponse> {
  return apiFetch<CancelJobResponse>(`/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
}
