import { create } from 'zustand'
import type {
  Conversation,
  Message,
  AgentTraceEntry,
  JobStatusUpdate,
} from '@/types/entities'

const MAX_CONVERSATIONS = 5
const MAX_TITLE_LENGTH = 48

function generateId(): string {
  return crypto.randomUUID()
}

function deriveTitle(firstUserMessage: string): string {
  const trimmed = firstUserMessage.trim()
  return trimmed.length > MAX_TITLE_LENGTH
    ? `${trimmed.slice(0, MAX_TITLE_LENGTH - 1)}…`
    : trimmed
}

interface ConversationsState {
  conversations: Conversation[]
  active_conversation_id: string | null
}

interface ConversationsActions {
  createConversation: () => string
  setActiveConversation: (id: string) => void
  appendMessage: (convId: string, message: Omit<Message, 'id' | 'created_at'>) => string
  updateMessage: (convId: string, msgId: string, patch: Partial<Message>) => void
  appendJobStatus: (convId: string, msgId: string, update: JobStatusUpdate) => void
  updateTrace: (convId: string, trace: AgentTraceEntry[]) => void
  setActiveJobId: (convId: string, jobId: string | null) => void
}

export const useConversationsStore = create<ConversationsState & ConversationsActions>()(
  (set) => ({
    conversations: [],
    active_conversation_id: null,

    createConversation: () => {
      const id = generateId()
      const conversation: Conversation = {
        id,
        title: 'New conversation',
        created_at: new Date(),
        messages: [],
        trace: [],
        active_job_id: null,
      }
      set((state) => {
        const trimmed =
          state.conversations.length >= MAX_CONVERSATIONS
            ? state.conversations.slice(0, MAX_CONVERSATIONS - 1)
            : state.conversations
        return {
          conversations: [conversation, ...trimmed],
          active_conversation_id: id,
        }
      })
      return id
    },

    setActiveConversation: (id) => {
      set({ active_conversation_id: id })
    },

    appendMessage: (convId, messageData) => {
      const id = generateId()
      const message: Message = {
        id,
        created_at: new Date(),
        ...messageData,
      }
      set((state) => ({
        conversations: state.conversations.map((conv) => {
          if (conv.id !== convId) return conv
          const isFirstUserMessage =
            message.role === 'user' && conv.messages.length === 0
          return {
            ...conv,
            title: isFirstUserMessage ? deriveTitle(message.content) : conv.title,
            messages: [...conv.messages, message],
          }
        }),
      }))
      return id
    },

    updateMessage: (convId, msgId, patch) => {
      set((state) => ({
        conversations: state.conversations.map((conv) => {
          if (conv.id !== convId) return conv
          return {
            ...conv,
            messages: conv.messages.map((msg) =>
              msg.id === msgId ? { ...msg, ...patch } : msg,
            ),
          }
        }),
      }))
    },

    appendJobStatus: (convId, msgId, update) => {
      set((state) => ({
        conversations: state.conversations.map((conv) => {
          if (conv.id !== convId) return conv
          return {
            ...conv,
            messages: conv.messages.map((msg) =>
              msg.id === msgId
                ? { ...msg, job_statuses: [...msg.job_statuses, update] }
                : msg,
            ),
          }
        }),
      }))
    },

    updateTrace: (convId, trace) => {
      set((state) => ({
        conversations: state.conversations.map((conv) =>
          conv.id === convId ? { ...conv, trace } : conv,
        ),
      }))
    },

    setActiveJobId: (convId, jobId) => {
      set((state) => ({
        conversations: state.conversations.map((conv) =>
          conv.id === convId ? { ...conv, active_job_id: jobId } : conv,
        ),
      }))
    },
  }),
)

export function selectActiveConversation(
  state: ConversationsState,
): Conversation | undefined {
  return state.conversations.find(
    (c) => c.id === state.active_conversation_id,
  )
}
