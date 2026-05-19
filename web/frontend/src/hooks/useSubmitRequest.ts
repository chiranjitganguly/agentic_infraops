import { useState, useCallback } from 'react'
import { submitRequest } from '@/api/requests'
import { ApiRequestError } from '@/api/client'
import { useConversationsStore } from '@/store/conversations'
import type { ErrorCode, ErrorPayload } from '@/types/entities'
import type {
  SubmitRequestResponse,
  FaqRoutedResponse,
  EnquiryRoutedResponse,
  ProvisioningRoutedResponse,
  ClarificationNeededResponse,
} from '@/types/api'

function isFaq(r: SubmitRequestResponse): r is FaqRoutedResponse {
  return (r as FaqRoutedResponse).intent === 'faq'
}

function isEnquiry(r: SubmitRequestResponse): r is EnquiryRoutedResponse {
  return (r as EnquiryRoutedResponse).intent === 'enquiry'
}

function isProvisioning(r: SubmitRequestResponse): r is ProvisioningRoutedResponse {
  return (r as ProvisioningRoutedResponse).intent === 'provision'
}

function isClarification(r: SubmitRequestResponse): r is ClarificationNeededResponse {
  return (r as ClarificationNeededResponse).status === 'clarification_needed'
}

function toErrorPayload(err: unknown): ErrorPayload {
  if (err instanceof ApiRequestError) {
    const code = err.body.error_code as ErrorCode
    return { error_code: code, message: err.body.message, http_status: err.status }
  }
  return {
    error_code: 'NETWORK_ERROR',
    message: 'Something went wrong — please try again.',
    http_status: 0,
  }
}

interface UseSubmitRequestReturn {
  isLoading: boolean
  submitQuery: (rawInput: string) => Promise<void>
  pendingInput: string | null
  setPendingInput: (v: string | null) => void
  lastSubmittedInput: string | null
}

export function useSubmitRequest(): UseSubmitRequestReturn {
  const [isLoading, setIsLoading] = useState(false)
  const [pendingInput, setPendingInput] = useState<string | null>(null)
  const [lastSubmittedInput, setLastSubmittedInput] = useState<string | null>(null)

  const {
    conversations,
    active_conversation_id,
    createConversation,
    appendMessage,
    updateMessage,
    updateTrace,
    setActiveJobId,
  } = useConversationsStore()

  const submitQuery = useCallback(
    async (rawInput: string) => {
      if (isLoading) return

      // Ensure there is an active conversation.
      let convId = active_conversation_id
      if (!convId || !conversations.find((c) => c.id === convId)) {
        convId = createConversation()
      }

      setIsLoading(true)
      setLastSubmittedInput(rawInput)

      // 1. Append user message immediately.
      appendMessage(convId, {
        role: 'user',
        content: rawInput,
        intent: null,
        infra_request_id: null,
        confirmation: null,
        clarification: null,
        error: null,
        job_statuses: [],
        loading: false,
      })

      // 2. Append placeholder assistant message showing loading indicator.
      const assistantMsgId = appendMessage(convId, {
        role: 'assistant',
        content: '',
        intent: null,
        infra_request_id: null,
        confirmation: null,
        clarification: null,
        error: null,
        job_statuses: [],
        loading: true,
      })

      try {
        const response = await submitRequest({ raw_input: rawInput })

        if (isFaq(response)) {
          updateMessage(convId, assistantMsgId, {
            loading: false,
            intent: 'faq',
            content: response.answer,
            infra_request_id: response.infra_request_id,
            faq_sources: response.sources,
          })
          updateTrace(convId, response.trace ?? [])
        } else if (isEnquiry(response)) {
          updateMessage(convId, assistantMsgId, {
            loading: false,
            intent: 'enquiry',
            content: response.answer,
            infra_request_id: response.infra_request_id,
            enquiry_data: {
              query_type: response.query_type,
              resource_type: response.resource_type,
              resource_name: response.resource_name,
              gcp_status: response.gcp_status,
              metadata: response.metadata,
              resources: response.resources,
              total_count: response.total_count,
            },
          })
          updateTrace(convId, response.trace ?? [])
        } else if (isProvisioning(response)) {
          const alreadyActive = response.status !== 'awaiting_confirmation'
          updateMessage(convId, assistantMsgId, {
            loading: false,
            intent: 'provision',
            content: '',
            infra_request_id: response.infra_request_id,
            confirmation: {
              intent_summary: response.intent_summary ?? null,
              intent: 'provision',
              confidence: null,
              job_id: response.job_id,
              confirmation_summary: response.confirmation_summary ?? null,
              expires_at: response.expires_at ?? null,
              // Mark as already confirmed so the timeline shows immediately
              confirmed: alreadyActive,
              cancelled: false,
            },
          })
          if (alreadyActive) {
            setActiveJobId(convId, response.job_id)
          }
          updateTrace(convId, response.trace ?? [])
        } else if (isClarification(response)) {
          updateMessage(convId, assistantMsgId, {
            loading: false,
            content: '',
            infra_request_id: response.infra_request_id,
            clarification: {
              infra_request_id: response.infra_request_id,
              question: response.clarification_question,
              round: response.clarification_round ?? 1,
              answered: false,
            },
          })
          updateTrace(convId, response.trace ?? [])
        } else {
          updateMessage(convId, assistantMsgId, {
            loading: false,
            error: {
              error_code: 'INTERNAL_ERROR',
              message: 'Received an unexpected response from the server.',
              http_status: 200,
            },
          })
        }
      } catch (err) {
        updateMessage(convId, assistantMsgId, {
          loading: false,
          error: toErrorPayload(err),
        })
      } finally {
        setIsLoading(false)
      }
    },
    [
      isLoading,
      active_conversation_id,
      conversations,
      createConversation,
      appendMessage,
      updateMessage,
      updateTrace,
      setLastSubmittedInput,
    ],
  )

  return { isLoading, submitQuery, pendingInput, setPendingInput, lastSubmittedInput }
}
