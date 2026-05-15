/**
 * Fetch-based SSE client for GET /jobs/{jobId}/stream.
 *
 * Native EventSource does not support custom headers, so we use fetch +
 * ReadableStream to carry the Authorization header. The SSE event format
 * emitted by the backend is:
 *   event: status\ndata: {"job_id":"...","status":"..."}\n\n
 *   event: done\ndata: \n\n
 */
import type { SseStatusEventData } from '@/types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL
const API_KEY = import.meta.env.VITE_API_KEY

interface JobStreamHandle {
  close: () => void
}

export function openJobStream(
  jobId: string,
  onStatus: (data: SseStatusEventData) => void,
  onDone: () => void,
  onError: () => void,
): JobStreamHandle {
  const controller = new AbortController()

  const run = async () => {
    let response: Response
    try {
      response = await fetch(`${BASE_URL}/jobs/${jobId}/stream`, {
        headers: {
          Authorization: `Bearer ${API_KEY}`,
          Accept: 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        signal: controller.signal,
      })
    } catch (err) {
      if ((err as Error).name !== 'AbortError') onError()
      return
    }

    if (!response.ok || !response.body) {
      onError()
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentData = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          onDone()
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            currentData = line.slice(5).trim()
          } else if (line === '') {
            // Blank line — dispatch the accumulated event.
            if (currentEvent === 'status' && currentData) {
              try {
                onStatus(JSON.parse(currentData) as SseStatusEventData)
              } catch {
                // Ignore malformed JSON — keep stream open.
              }
            } else if (currentEvent === 'done') {
              onDone()
              controller.abort()
              return
            }
            currentEvent = ''
            currentData = ''
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') onError()
    }
  }

  run()
  return { close: () => controller.abort() }
}
