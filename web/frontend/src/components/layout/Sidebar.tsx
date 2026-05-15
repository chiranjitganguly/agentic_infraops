import { Plus } from 'lucide-react'
import { useConversationsStore } from '@/store/conversations'

export function Sidebar() {
  const conversations = useConversationsStore((s) => s.conversations)
  const activeId = useConversationsStore((s) => s.active_conversation_id)
  const createConversation = useConversationsStore((s) => s.createConversation)
  const setActiveConversation = useConversationsStore((s) => s.setActiveConversation)

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-700">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Conversations
        </span>
        <button
          onClick={() => createConversation()}
          aria-label="New conversation"
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          New
        </button>
      </div>

      {/* Conversation list */}
      <nav aria-label="Conversation history" className="flex-1 overflow-y-auto py-2">
        {conversations.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-slate-400 dark:text-slate-500">
            No conversations yet
          </p>
        ) : (
          <ul>
            {conversations.map((conv) => {
              const isActive = conv.id === activeId
              return (
                <li key={conv.id}>
                  <button
                    onClick={() => setActiveConversation(conv.id)}
                    aria-current={isActive ? 'page' : undefined}
                    className={[
                      'w-full truncate px-3 py-2 text-left text-sm transition-colors',
                      isActive
                        ? 'bg-blue-50 font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300'
                        : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700',
                    ].join(' ')}
                  >
                    {conv.title}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </nav>
    </div>
  )
}
