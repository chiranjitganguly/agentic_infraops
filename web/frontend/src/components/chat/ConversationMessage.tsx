import { useCallback } from 'react'
import { MessageBubble } from './MessageBubble'
import { IntentConfirmationCard } from '@/components/cards/IntentConfirmationCard'
import { EnquiryConfirmationCard } from '@/components/cards/EnquiryConfirmationCard'
import { ClarificationCard } from '@/components/cards/ClarificationCard'
import { useJobStream } from '@/hooks/useJobStream'
import { useConversationsStore } from '@/store/conversations'
import { confirmJob, cancelJob } from '@/api/jobs'
import { clarifyRequest } from '@/api/requests'
import type { Message } from '@/types/entities'
import type { SubmitRequestResponse } from '@/types/api'

interface ConversationMessageProps {
  message: Message
  conversationId: string
  setPendingInput: (v: string | null) => void
  originalInput: string | null
  onClarificationResponse: (response: SubmitRequestResponse, msgId: string, convId: string) => void
  onJobConfirmed?: (jobId: string) => void
}

function routeResponse(
  response: SubmitRequestResponse,
  msgId: string,
  convId: string,
  updateMessage: ReturnType<typeof useConversationsStore.getState>['updateMessage'],
) {
  const r = response as unknown as Record<string, unknown>
  if (r.intent === 'faq') {
    updateMessage(convId, msgId, {
      loading: false,
      intent: 'faq',
      content: r.answer as string,
      faq_sources: (r.sources as string[]) ?? [],
    })
  } else if (r.intent === 'enquiry') {
    updateMessage(convId, msgId, {
      loading: false,
      intent: 'enquiry',
      content: r.answer as string,
    })
  } else if (r.intent === 'provision') {
    updateMessage(convId, msgId, {
      loading: false,
      intent: 'provision',
      content: '',
      confirmation: {
        intent_summary: (r.intent_summary as string | null) ?? null,
        intent: 'provision',
        confidence: null,
        job_id: r.job_id as string | null,
        confirmation_summary: (r.confirmation_summary as Record<string, unknown> | null) ?? null,
        expires_at: (r.expires_at as string | null) ?? null,
        confirmed: false,
        cancelled: false,
      },
    })
  } else if (r.status === 'clarification_needed') {
    updateMessage(convId, msgId, {
      loading: false,
      clarification: {
        infra_request_id: r.infra_request_id as string,
        question: r.clarification_question as string,
        round: (r.clarification_round as number | undefined) ?? 1,
        answered: false,
      },
    })
  }
}

export function ConversationMessage({
  message,
  conversationId,
  setPendingInput,
  originalInput,
  onJobConfirmed,
}: ConversationMessageProps) {
  const { updateMessage, setActiveJobId } = useConversationsStore()

  const confirmation = message.confirmation
  const jobId = confirmation?.job_id ?? null
  const sseEnabled =
    confirmation?.confirmed === true && !confirmation.cancelled && jobId !== null

  const { sseState, retry } = useJobStream({
    jobId,
    conversationId,
    messageId: message.id,
    enabled: sseEnabled,
  })

  // --- Confirmation handlers ---

  const handleProvisionConfirm = useCallback(async () => {
    if (!jobId) return
    try {
      await confirmJob(jobId)
      updateMessage(conversationId, message.id, {
        confirmation: confirmation ? { ...confirmation, confirmed: true } : null,
      })
      setActiveJobId(conversationId, jobId)
      onJobConfirmed?.(jobId)
    } catch {
      updateMessage(conversationId, message.id, {
        loading: false,
        error: {
          error_code: 'CONFIRM_FAILED',
          message: 'Could not confirm this job — it may have expired. Please submit a new request.',
          http_status: 409,
        },
      })
    }
  }, [jobId, conversationId, message.id, confirmation, updateMessage, setActiveJobId, onJobConfirmed])

  const handleRephrase = useCallback(async () => {
    if (!jobId) return
    try {
      await cancelJob(jobId)
    } catch {
      // Ignore cancellation errors — still restore the input.
    }
    updateMessage(conversationId, message.id, {
      confirmation: confirmation ? { ...confirmation, cancelled: true } : null,
    })
    setPendingInput(originalInput ?? '')
  }, [jobId, conversationId, message.id, confirmation, updateMessage, setPendingInput, originalInput])

  const handleProvisionExpired = useCallback(async () => {
    if (!jobId) return
    try {
      await cancelJob(jobId)
    } catch {
      // Swallow — expiry UI is shown by CountdownTimer callback.
    }
  }, [jobId])

  const handleEnquiryConfirm = useCallback(() => {
    if (!confirmation) return
    updateMessage(conversationId, message.id, {
      confirmation: { ...confirmation, confirmed: true },
    })
  }, [conversationId, message.id, confirmation, updateMessage])

  const handleEnquiryRephrase = useCallback(() => {
    updateMessage(conversationId, message.id, {
      confirmation: confirmation ? { ...confirmation, cancelled: true } : null,
    })
    setPendingInput(originalInput ?? '')
  }, [conversationId, message.id, confirmation, updateMessage, setPendingInput, originalInput])

  // --- Clarification handler ---

  const handleClarificationSubmit = useCallback(async (answer: string) => {
    const clarification = message.clarification
    if (!clarification) return

    updateMessage(conversationId, message.id, { clarification: { ...clarification, answered: true } })

    try {
      const response = await clarifyRequest(clarification.infra_request_id, { clarification: answer })
      routeResponse(response, message.id, conversationId, updateMessage)
    } catch {
      updateMessage(conversationId, message.id, {
        error: {
          error_code: 'INTERNAL_ERROR',
          message: 'Something went wrong — please try again.',
          http_status: 500,
        },
      })
    }
  }, [conversationId, message.id, message.clarification, updateMessage])

  // --- Build card slots ---

  let confirmationSlot: React.ReactNode = null
  let clarificationSlot: React.ReactNode = null

  if (confirmation && confirmation.intent === 'provision') {
    confirmationSlot = (
      <IntentConfirmationCard
        confirmation={confirmation}
        onConfirm={handleProvisionConfirm}
        onRephrase={handleRephrase}
        onExpired={handleProvisionExpired}
      />
    )
  } else if (confirmation && confirmation.intent === 'enquiry') {
    confirmationSlot = (
      <EnquiryConfirmationCard
        confirmation={confirmation}
        onConfirm={handleEnquiryConfirm}
        onRephrase={handleEnquiryRephrase}
      />
    )
  }

  if (message.clarification) {
    clarificationSlot = (
      <ClarificationCard
        clarification={message.clarification}
        onSubmit={handleClarificationSubmit}
      />
    )
  }

  return (
    <MessageBubble
      message={message}
      confirmationSlot={confirmationSlot}
      clarificationSlot={clarificationSlot}
      sseState={sseState}
      onSseRetry={retry}
    />
  )
}
