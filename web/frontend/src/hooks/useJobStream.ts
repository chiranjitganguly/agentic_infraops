import { useCallback, useEffect, useRef, useState } from 'react'
import { openJobStream } from '@/api/sse'
import { useConversationsStore } from '@/store/conversations'
import type { SseStreamState } from '@/types/entities'
import type { SseStatusEventData } from '@/types/api'

const MAX_RETRIES = 3
const RETRY_DELAYS_MS = [1000, 2000, 3000]

interface UseJobStreamOptions {
  jobId: string | null
  conversationId: string
  messageId: string
  enabled: boolean
}

interface UseJobStreamResult {
  sseState: SseStreamState
  retry: () => void
}

export function useJobStream({
  jobId,
  conversationId,
  messageId,
  enabled,
}: UseJobStreamOptions): UseJobStreamResult {
  const [sseState, setSseState] = useState<SseStreamState>('idle')
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const streamHandleRef = useRef<{ close: () => void } | null>(null)

  const appendJobStatus = useConversationsStore((s) => s.appendJobStatus)
  const updateTrace = useConversationsStore((s) => s.updateTrace)

  const clearRetryTimer = () => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }

  const startStream = useCallback(() => {
    if (!jobId) return

    setSseState('connecting')

    const handle = openJobStream(
      jobId,
      (data: SseStatusEventData) => {
        retryCountRef.current = 0
        setSseState('open')
        appendJobStatus(conversationId, messageId, {
          job_id: data.job_id,
          status: data.status,
          received_at: new Date(),
        })
        if (data.trace && data.trace.length > 0) {
          updateTrace(conversationId, data.trace)
        }
      },
      () => {
        setSseState('closed')
        handle.close()
      },
      () => {
        handle.close()
        if (retryCountRef.current < MAX_RETRIES) {
          const delay = RETRY_DELAYS_MS[retryCountRef.current]
          retryCountRef.current += 1
          setSseState('connecting')
          retryTimerRef.current = setTimeout(startStream, delay)
        } else {
          setSseState('failed')
        }
      },
    )

    streamHandleRef.current = handle
  }, [jobId, conversationId, messageId, appendJobStatus, updateTrace])

  useEffect(() => {
    if (!enabled || !jobId) return

    retryCountRef.current = 0
    startStream()

    return () => {
      clearRetryTimer()
      streamHandleRef.current?.close()
    }
  }, [enabled, jobId, startStream])

  const retry = useCallback(() => {
    clearRetryTimer()
    streamHandleRef.current?.close()
    retryCountRef.current = 0
    startStream()
  }, [startStream])

  return { sseState, retry }
}
