import { useCallback, useEffect, useState } from 'react'
import { useConversationsStore, selectActiveConversation } from '@/store/conversations'
import { useSubmitRequest } from '@/hooks/useSubmitRequest'
import { MessageList } from './MessageList'
import { InputComposer } from './InputComposer'
import { TracePanel } from '@/components/trace/TracePanel'
import { JobStatusPanel } from '@/components/jobs/JobStatusPanel'

type ActiveView = 'chat' | 'jobs'

export function ChatWindow() {
  const activeConversation = useConversationsStore(selectActiveConversation)
  const { isLoading, submitQuery, pendingInput, setPendingInput, lastSubmittedInput } = useSubmitRequest()

  const [activeView, setActiveView] = useState<ActiveView>('chat')
  const [toastJobId, setToastJobId] = useState<string | null>(null)
  const [toastVisible, setToastVisible] = useState(false)

  const messages = activeConversation?.messages ?? []
  const convId = activeConversation?.id ?? ''
  const trace = activeConversation?.trace ?? []

  function handleSubmit(text: string) {
    setPendingInput(null)
    submitQuery(text)
  }

  const handleJobConfirmed = useCallback((jobId: string) => {
    setToastJobId(jobId)
    setToastVisible(true)
  }, [])

  useEffect(() => {
    if (!toastVisible) return
    const t = setTimeout(() => setToastVisible(false), 5000)
    return () => clearTimeout(t)
  }, [toastVisible])

  return (
    <section className="flex flex-1 flex-col overflow-hidden" aria-label="Chat conversation">
      {/* Tab bar */}
      <div className="flex shrink-0 items-center gap-1 border-b border-slate-200 bg-white px-4 dark:border-slate-700 dark:bg-slate-900">
        <TabButton active={activeView === 'chat'} onClick={() => setActiveView('chat')}>
          Chat
        </TabButton>
        <TabButton active={activeView === 'jobs'} onClick={() => setActiveView('jobs')}>
          Job Status
        </TabButton>
      </div>

      {/* Toast notification */}
      {toastVisible && toastJobId && (
        <div
          role="status"
          aria-live="polite"
          className="mx-4 mt-3 flex items-start justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 shadow-sm dark:border-green-800 dark:bg-green-950/40"
        >
          <div className="flex items-start gap-2">
            <svg className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <div>
              <p className="text-sm font-semibold text-green-700 dark:text-green-400">
                Job submitted successfully
              </p>
              <p className="mt-0.5 font-mono text-xs text-green-600 dark:text-green-500 break-all select-all">
                {toastJobId}
              </p>
            </div>
          </div>
          <button
            onClick={() => setToastVisible(false)}
            className="shrink-0 text-green-500 hover:text-green-700 dark:hover:text-green-300"
            aria-label="Dismiss"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Chat view */}
      {activeView === 'chat' && (
        <>
          <MessageList
            messages={messages}
            conversationId={convId}
            setPendingInput={setPendingInput}
            originalInput={lastSubmittedInput}
            onJobConfirmed={handleJobConfirmed}
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
        </>
      )}

      {/* Job status search view */}
      {activeView === 'jobs' && <JobStatusPanel />}
    </section>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'relative px-3 py-2.5 text-sm font-medium transition-colors',
        active
          ? 'text-blue-600 dark:text-blue-400'
          : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200',
      ].join(' ')}
    >
      {children}
      {active && (
        <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-blue-600 dark:bg-blue-400" />
      )}
    </button>
  )
}
