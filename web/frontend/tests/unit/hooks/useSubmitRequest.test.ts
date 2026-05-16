import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSubmitRequest } from '@/hooks/useSubmitRequest'
import { useConversationsStore } from '@/store/conversations'

// Mock the requests API module so no real HTTP calls happen.
vi.mock('@/api/requests', () => ({
  submitRequest: vi.fn(),
}))

import { submitRequest } from '@/api/requests'
import { ApiRequestError } from '@/api/client'
import type { ApiError } from '@/types/api'

const mockSubmitRequest = vi.mocked(submitRequest)

function resetStore() {
  useConversationsStore.setState({
    conversations: [],
    active_conversation_id: null,
  })
}

describe('useSubmitRequest', () => {
  beforeEach(() => {
    resetStore()
    mockSubmitRequest.mockReset()
  })

  it('starts with isLoading = false', () => {
    const { result } = renderHook(() => useSubmitRequest())
    expect(result.current.isLoading).toBe(false)
  })

  it('creates a conversation and appends user + assistant messages on FAQ response', async () => {
    mockSubmitRequest.mockResolvedValueOnce({
      infra_request_id: 'req-1',
      intent: 'faq',
      status: 'answered',
      answer: 'Use VPC peering for cross-project connectivity.',
      sources: ['docs/networking.md'],
      correlation_id: 'corr-1',
    })

    const { result } = renderHook(() => useSubmitRequest())

    await act(async () => {
      await result.current.submitQuery('What is VPC peering?')
    })

    const state = useConversationsStore.getState()
    expect(state.conversations).toHaveLength(1)

    const conv = state.conversations[0]
    expect(conv.messages).toHaveLength(2)

    const [userMsg, assistantMsg] = conv.messages
    expect(userMsg.role).toBe('user')
    expect(userMsg.content).toBe('What is VPC peering?')

    expect(assistantMsg.role).toBe('assistant')
    expect(assistantMsg.intent).toBe('faq')
    expect(assistantMsg.content).toBe('Use VPC peering for cross-project connectivity.')
    expect(assistantMsg.faq_sources).toEqual(['docs/networking.md'])
    expect(assistantMsg.loading).toBe(false)
    expect(assistantMsg.error).toBeNull()
  })

  it('appends an ErrorPayload on 4xx response', async () => {
    const apiError: ApiError = {
      error_code: 'VALIDATION_ERROR',
      message: 'Region invalid-region-xyz is not allowed.',
      details: {},
      correlation_id: null,
      timestamp: new Date().toISOString(),
    }
    mockSubmitRequest.mockRejectedValueOnce(new ApiRequestError(400, apiError))

    const { result } = renderHook(() => useSubmitRequest())

    await act(async () => {
      await result.current.submitQuery('Create VM in invalid-region-xyz')
    })

    const conv = useConversationsStore.getState().conversations[0]
    const assistantMsg = conv.messages[1]

    expect(assistantMsg.loading).toBe(false)
    expect(assistantMsg.error).not.toBeNull()
    expect(assistantMsg.error?.error_code).toBe('VALIDATION_ERROR')
    expect(assistantMsg.error?.http_status).toBe(400)
  })

  it('sets NETWORK_ERROR on fetch failure', async () => {
    mockSubmitRequest.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    const { result } = renderHook(() => useSubmitRequest())

    await act(async () => {
      await result.current.submitQuery('Any query')
    })

    const conv = useConversationsStore.getState().conversations[0]
    const assistantMsg = conv.messages[1]

    expect(assistantMsg.error?.error_code).toBe('NETWORK_ERROR')
    expect(assistantMsg.error?.http_status).toBe(0)
  })

  it('sets isLoading = true during inflight request and false afterwards', async () => {
    let resolveRequest!: (v: unknown) => void
    mockSubmitRequest.mockReturnValueOnce(
      new Promise((resolve) => { resolveRequest = resolve }),
    )

    const { result } = renderHook(() => useSubmitRequest())
    const loadingStates: boolean[] = []

    act(() => {
      result.current.submitQuery('Slow query')
    })

    // Immediately after calling submitQuery the hook should be loading.
    loadingStates.push(result.current.isLoading)

    await act(async () => {
      resolveRequest({
        infra_request_id: 'req-2',
        intent: 'faq',
        status: 'answered',
        answer: 'Done.',
        sources: [],
        correlation_id: 'corr-2',
      })
    })

    loadingStates.push(result.current.isLoading)
    expect(loadingStates).toEqual([true, false])
  })

  it('sets enquiry intent and enquiry_data on enquiry response', async () => {
    mockSubmitRequest.mockResolvedValueOnce({
      infra_request_id: 'req-3',
      intent: 'enquiry',
      query_type: 'single',
      status: 'answered',
      answer: 'vm-web-01 is RUNNING.',
      queried_at: new Date().toISOString(),
      correlation_id: 'corr-3',
      resource_type: 'compute_instance',
      resource_name: 'vm-web-01',
      gcp_status: 'RUNNING',
    })

    const { result } = renderHook(() => useSubmitRequest())
    await act(async () => { await result.current.submitQuery('Status of vm-web-01?') })

    const msg = useConversationsStore.getState().conversations[0].messages[1]
    expect(msg.intent).toBe('enquiry')
    expect(msg.enquiry_data?.resource_name).toBe('vm-web-01')
    expect(msg.enquiry_data?.gcp_status).toBe('RUNNING')
  })

  it('sets clarification payload on clarification_needed response', async () => {
    mockSubmitRequest.mockResolvedValueOnce({
      infra_request_id: 'req-4',
      status: 'clarification_needed',
      clarification_question: 'Which region should the VM be created in?',
      correlation_id: 'corr-4',
    })

    const { result } = renderHook(() => useSubmitRequest())
    await act(async () => { await result.current.submitQuery('Create a VM') })

    const msg = useConversationsStore.getState().conversations[0].messages[1]
    expect(msg.clarification).not.toBeNull()
    expect(msg.clarification?.question).toBe('Which region should the VM be created in?')
    expect(msg.clarification?.round).toBe(1)
    expect(msg.clarification?.answered).toBe(false)
  })
})
