import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TracePanel } from '@/components/trace/TracePanel'
import type { AgentTraceEntry } from '@/types/entities'

function makeEntry(overrides: Partial<AgentTraceEntry> = {}): AgentTraceEntry {
  return {
    agent_name: 'TestAgent',
    role: null,
    status: 'completed',
    duration_ms: null,
    ...overrides,
  }
}

const SAMPLE_TRACE: AgentTraceEntry[] = [
  makeEntry({ agent_name: 'IntentAnalyzerAgent', status: 'completed', duration_ms: 120 }),
  makeEntry({ agent_name: 'InfraDiagnosticsAgent', status: 'running', role: 'diagnostics' }),
  makeEntry({ agent_name: 'KnowledgeRetrievalAgent', status: 'pending' }),
]

describe('TracePanel', () => {
  it('renders collapsed by default — trace list not visible', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    expect(screen.queryByRole('list', { name: /agent execution trace/i })).not.toBeInTheDocument()
  })

  it('shows step count in toggle button', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    expect(screen.getByText('3 steps')).toBeInTheDocument()
  })

  it('expands on click and renders all entries', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    fireEvent.click(screen.getByRole('button', { name: /agent trace/i }))

    expect(screen.getByRole('list', { name: /agent execution trace/i })).toBeInTheDocument()
    expect(screen.getByText('IntentAnalyzerAgent')).toBeInTheDocument()
    expect(screen.getByText('InfraDiagnosticsAgent')).toBeInTheDocument()
    expect(screen.getByText('KnowledgeRetrievalAgent')).toBeInTheDocument()
  })

  it('shows distinct status labels for each entry', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    fireEvent.click(screen.getByRole('button', { name: /agent trace/i }))

    expect(screen.getAllByText('completed').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('running').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('pending').length).toBeGreaterThanOrEqual(1)
  })

  it('shows role text when entry has a role', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    fireEvent.click(screen.getByRole('button', { name: /agent trace/i }))
    expect(screen.getByText('diagnostics')).toBeInTheDocument()
  })

  it('shows duration when provided', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    fireEvent.click(screen.getByRole('button', { name: /agent trace/i }))
    expect(screen.getByText('120ms')).toBeInTheDocument()
  })

  it('collapses again on second click', () => {
    render(<TracePanel trace={SAMPLE_TRACE} />)
    const button = screen.getByRole('button', { name: /agent trace/i })
    fireEvent.click(button) // open
    fireEvent.click(button) // close
    expect(screen.queryByRole('list', { name: /agent execution trace/i })).not.toBeInTheDocument()
  })

  it('shows "No trace available" placeholder when trace is empty', () => {
    render(<TracePanel trace={[]} />)
    fireEvent.click(screen.getByRole('button', { name: /agent trace/i }))
    expect(screen.getByText(/No trace available/i)).toBeInTheDocument()
  })

  it('does not show step count when trace is empty', () => {
    render(<TracePanel trace={[]} />)
    expect(screen.queryByText(/steps?/i)).not.toBeInTheDocument()
  })
})
