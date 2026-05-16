import { useEffect, useRef } from 'react'
import type { Message } from '@/types/entities'
import { ConversationMessage } from './ConversationMessage'

interface MessageListProps {
  messages: Message[]
  conversationId: string
  setPendingInput: (v: string | null) => void
  originalInput: string | null
  onJobConfirmed?: (jobId: string) => void
}

export function MessageList({
  messages,
  conversationId,
  setPendingInput,
  originalInput,
  onJobConfirmed,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
        <div className="text-3xl" aria-hidden="true">🏗️</div>
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Ask about your infrastructure
        </p>
        <p className="max-w-xs text-xs text-slate-500 dark:text-slate-400">
          Check resource status, provision new VMs or buckets, or ask a best-practice question.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4 scrollbar-thin">
      {messages.map((message) => (
        <ConversationMessage
          key={message.id}
          message={message}
          conversationId={conversationId}
          setPendingInput={setPendingInput}
          originalInput={originalInput}
          onClarificationResponse={() => {}}
          onJobConfirmed={onJobConfirmed}
        />
      ))}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  )
}
