import { apiFetch } from './client'
import type {
  SubmitRequestBody,
  SubmitRequestResponse,
  ClarifyBody,
} from '@/types/api'

export function submitRequest(
  body: SubmitRequestBody,
): Promise<SubmitRequestResponse> {
  return apiFetch<SubmitRequestResponse>('/requests', {
    method: 'POST',
    body: JSON.stringify({ channel: 'web', ...body }),
  })
}

export function clarifyRequest(
  infraRequestId: string,
  body: ClarifyBody,
): Promise<SubmitRequestResponse> {
  return apiFetch<SubmitRequestResponse>(
    `/requests/${infraRequestId}/clarify`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}
