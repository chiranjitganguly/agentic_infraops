import { apiFetch } from './client'
import type { ConfirmJobResponse, CancelJobResponse, GetJobResponse } from '@/types/api'

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

export function getJob(jobId: string): Promise<GetJobResponse> {
  return apiFetch<GetJobResponse>(`/jobs/${jobId}`)
}
