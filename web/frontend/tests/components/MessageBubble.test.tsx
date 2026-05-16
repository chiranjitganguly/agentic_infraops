import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageBubble } from '@/components/chat/MessageBubble'
import type { Message } from '@/types/entities'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: '',
    created_at: new Date(),
    intent: null,
    infra_request_id: null,
    confirmation: null,
    clarification: null,
    error: null,
    job_statuses: [],
    loading: false,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('MessageBubble — loading', () => {
  it('shows loading indicator when loading=true', () => {
    render(<MessageBubble message={makeMessage({ loading: true })} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('does not show content while loading', () => {
    render(<MessageBubble message={makeMessage({ loading: true, content: 'Should not show' })} />)
    expect(screen.queryByText('Should not show')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Error states (T035 — FR-020a–d)
// ---------------------------------------------------------------------------

describe('MessageBubble — error states', () => {
  it('GUARDRAIL_VIOLATION: shows backend message verbatim', () => {
    const msg = makeMessage({
      error: {
        error_code: 'GUARDRAIL_VIOLATION',
        message: 'machine_type n2-standard-96 exceeds your role limits.',
        http_status: 403,
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/n2-standard-96 exceeds your role limits/)).toBeInTheDocument()
    expect(screen.getByText(/platform engineer/i)).toBeInTheDocument()
  })

  it('RATE_LIMIT_EXCEEDED: shows midnight UTC message', () => {
    const msg = makeMessage({
      error: {
        error_code: 'RATE_LIMIT_EXCEEDED',
        message: 'Daily provisioning limit reached.',
        http_status: 429,
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/midnight UTC/i)).toBeInTheDocument()
  })

  it('VALIDATION_ERROR: shows backend message and rephrase hint', () => {
    const msg = makeMessage({
      error: {
        error_code: 'VALIDATION_ERROR',
        message: 'Region invalid-region-xyz is not recognised.',
        http_status: 400,
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText(/invalid-region-xyz is not recognised/)).toBeInTheDocument()
    expect(screen.getByText(/rephrasing/i)).toBeInTheDocument()
  })

  it('INTERNAL_ERROR: shows generic message without raw detail', () => {
    const msg = makeMessage({
      error: {
        error_code: 'INTERNAL_ERROR',
        message: 'Stack trace: NullPointerException at line 42',
        http_status: 500,
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText(/NullPointerException/)).not.toBeInTheDocument()
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument()
  })

  it('NETWORK_ERROR: shows generic message', () => {
    const msg = makeMessage({
      error: {
        error_code: 'NETWORK_ERROR',
        message: 'Failed to fetch',
        http_status: 0,
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// FAQ answer
// ---------------------------------------------------------------------------

describe('MessageBubble — FAQ answer', () => {
  it('renders FAQ answer text', () => {
    const msg = makeMessage({
      intent: 'faq',
      content: 'Use VPC peering for cross-project traffic.',
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText(/VPC peering for cross-project/)).toBeInTheDocument()
  })

  it('shows sources toggle when sources present', () => {
    const msg = makeMessage({
      intent: 'faq',
      content: 'Use shared VPC.',
      faq_sources: ['docs/networking.md', 'docs/vpc.md'],
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText(/Show sources \(2\)/i)).toBeInTheDocument()
  })

  it('does not render sources toggle when sources is empty', () => {
    const msg = makeMessage({
      intent: 'faq',
      content: 'No external references needed.',
      faq_sources: [],
    })
    render(<MessageBubble message={msg} />)
    expect(screen.queryByText(/Show sources/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// User message
// ---------------------------------------------------------------------------

describe('MessageBubble — user message', () => {
  it('renders user message content', () => {
    const msg = makeMessage({ role: 'user', content: 'What is the status of vm-web-01?' })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText('What is the status of vm-web-01?')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Enquiry answer
// ---------------------------------------------------------------------------

describe('MessageBubble — enquiry answer', () => {
  it('renders resource name and gcp_status for single query', () => {
    const msg = makeMessage({
      intent: 'enquiry',
      content: 'vm-web-01 is running.',
      enquiry_data: {
        query_type: 'single',
        resource_type: 'compute_instance',
        resource_name: 'vm-web-01',
        gcp_status: 'RUNNING',
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText('vm-web-01 is running.')).toBeInTheDocument()
    expect(screen.getByText('vm-web-01')).toBeInTheDocument()
    expect(screen.getByText('RUNNING')).toBeInTheDocument()
  })

  it('renders total_count for list query', () => {
    const msg = makeMessage({
      intent: 'enquiry',
      content: 'Found 3 VMs.',
      enquiry_data: {
        query_type: 'list',
        resource_type: 'compute_instance',
        total_count: 3,
        resources: [],
      },
    })
    render(<MessageBubble message={msg} />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })
})
