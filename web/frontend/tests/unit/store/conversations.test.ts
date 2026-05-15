import { describe, it, expect, beforeEach } from 'vitest'
import { useConversationsStore } from '@/store/conversations'

function resetStore() {
  useConversationsStore.setState({ conversations: [], active_conversation_id: null })
}

describe('conversations store', () => {
  beforeEach(resetStore)

  // -------------------------------------------------------------------------
  // createConversation
  // -------------------------------------------------------------------------

  it('creates a conversation and sets it as active', () => {
    const id = useConversationsStore.getState().createConversation()
    const state = useConversationsStore.getState()
    expect(state.active_conversation_id).toBe(id)
    expect(state.conversations).toHaveLength(1)
    expect(state.conversations[0].id).toBe(id)
  })

  it('prepends new conversations (newest-first order)', () => {
    const id1 = useConversationsStore.getState().createConversation()
    const id2 = useConversationsStore.getState().createConversation()
    const state = useConversationsStore.getState()
    expect(state.conversations[0].id).toBe(id2)
    expect(state.conversations[1].id).toBe(id1)
  })

  it('new conversation starts with default title "New conversation"', () => {
    useConversationsStore.getState().createConversation()
    const conv = useConversationsStore.getState().conversations[0]
    expect(conv.title).toBe('New conversation')
  })

  // -------------------------------------------------------------------------
  // 5-cap eviction (T060)
  // -------------------------------------------------------------------------

  it('enforces 5-conversation cap — 6th creation drops the oldest', () => {
    const ids: string[] = []
    for (let i = 0; i < 5; i++) {
      ids.push(useConversationsStore.getState().createConversation())
    }
    // 5 conversations exist; ids[0] is the oldest (now last in newest-first list)
    const oldestId = ids[0]

    useConversationsStore.getState().createConversation() // triggers eviction

    const state = useConversationsStore.getState()
    expect(state.conversations).toHaveLength(5)
    expect(state.conversations.find((c) => c.id === oldestId)).toBeUndefined()
  })

  it('does not evict when fewer than 5 conversations exist', () => {
    for (let i = 0; i < 4; i++) {
      useConversationsStore.getState().createConversation()
    }
    useConversationsStore.getState().createConversation()
    expect(useConversationsStore.getState().conversations).toHaveLength(5)
  })

  // -------------------------------------------------------------------------
  // Auto-generated title (T061)
  // -------------------------------------------------------------------------

  it('derives title from first user message content', () => {
    const convId = useConversationsStore.getState().createConversation()
    useConversationsStore.getState().appendMessage(convId, {
      role: 'user',
      content: 'What is the status of my VM?',
      intent: null,
      infra_request_id: null,
      confirmation: null,
      clarification: null,
      error: null,
      job_statuses: [],
      loading: false,
    })
    const conv = useConversationsStore.getState().conversations.find((c) => c.id === convId)!
    expect(conv.title).toBe('What is the status of my VM?')
  })

  it('truncates title at 48 characters with ellipsis', () => {
    const convId = useConversationsStore.getState().createConversation()
    const longContent = 'A'.repeat(60)
    useConversationsStore.getState().appendMessage(convId, {
      role: 'user',
      content: longContent,
      intent: null,
      infra_request_id: null,
      confirmation: null,
      clarification: null,
      error: null,
      job_statuses: [],
      loading: false,
    })
    const conv = useConversationsStore.getState().conversations.find((c) => c.id === convId)!
    expect(conv.title.length).toBeLessThanOrEqual(49) // 48 chars + ellipsis char = 49
    expect(conv.title).toMatch(/…$/)
  })

  it('does not change title on second user message', () => {
    const convId = useConversationsStore.getState().createConversation()
    useConversationsStore.getState().appendMessage(convId, {
      role: 'user',
      content: 'First message',
      intent: null,
      infra_request_id: null,
      confirmation: null,
      clarification: null,
      error: null,
      job_statuses: [],
      loading: false,
    })
    useConversationsStore.getState().appendMessage(convId, {
      role: 'user',
      content: 'Second message — should not override title',
      intent: null,
      infra_request_id: null,
      confirmation: null,
      clarification: null,
      error: null,
      job_statuses: [],
      loading: false,
    })
    const conv = useConversationsStore.getState().conversations.find((c) => c.id === convId)!
    expect(conv.title).toBe('First message')
  })

  it('does not set title from assistant messages', () => {
    const convId = useConversationsStore.getState().createConversation()
    useConversationsStore.getState().appendMessage(convId, {
      role: 'assistant',
      content: 'Assistant message should not become title',
      intent: null,
      infra_request_id: null,
      confirmation: null,
      clarification: null,
      error: null,
      job_statuses: [],
      loading: false,
    })
    const conv = useConversationsStore.getState().conversations.find((c) => c.id === convId)!
    expect(conv.title).toBe('New conversation')
  })

  // -------------------------------------------------------------------------
  // setActiveConversation (T058)
  // -------------------------------------------------------------------------

  it('setActiveConversation changes the active id', () => {
    const id1 = useConversationsStore.getState().createConversation()
    const id2 = useConversationsStore.getState().createConversation()
    // id2 is active by default after creation
    expect(useConversationsStore.getState().active_conversation_id).toBe(id2)

    useConversationsStore.getState().setActiveConversation(id1)
    expect(useConversationsStore.getState().active_conversation_id).toBe(id1)
  })
})
