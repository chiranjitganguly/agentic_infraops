import { useConversationsStore, selectActiveConversation } from '@/store/conversations'
import { useSubmitRequest } from '@/hooks/useSubmitRequest'
import { MessageList } from './MessageList'
import { InputComposer } from './InputComposer'
import { TracePanel } from '@/components/trace/TracePanel'

export function ChatWindow() {
  const activeConversation = useConversationsStore(selectActiveConversation)
  const { isLoading, submitQuery, pendingInput, setPendingInput, lastSubmittedInput } = useSubmitRequest()

  const messages = activeConversation?.messages ?? []
  const convId = activeConversation?.id ?? ''
  const trace = activeConversation?.trace ?? []

  function handleSubmit(text: string) {
    setPendingInput(null)
    submitQuery(text)
  }

  return (
    <section
      className="flex flex-1 flex-col overflow-hidden"
      aria-label="Chat conversation"
    >
      <MessageList
        messages={messages}
        conversationId={convId}
        setPendingInput={setPendingInput}
        originalInput={lastSubmittedInput}
      />
      <div className="border-t border-surface-border px-4 pb-2">
        <TracePanel trace={trace} />
      </div>
      <InputComposer
        onSubmit={handleSubmit}
        loading={isLoading}
        initialValue={pendingInput ?? ''}
        key={pendingInput ?? 'default'}
      />
    </section>
  )
}
