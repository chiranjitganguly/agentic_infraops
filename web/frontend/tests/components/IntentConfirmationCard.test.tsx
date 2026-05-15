import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { IntentConfirmationCard } from '@/components/cards/IntentConfirmationCard'
import type { IntentConfirmation } from '@/types/entities'

function makeConfirmation(overrides: Partial<IntentConfirmation> = {}): IntentConfirmation {
  return {
    intent_summary: 'Create a VM in us-central1 with 4 CPUs.',
    intent: 'provision',
    confidence: 0.95,
    job_id: 'job-abc',
    confirmation_summary: { region: 'us-central1', machine_type: 'n2-standard-4' },
    expires_at: null,
    confirmed: false,
    cancelled: false,
    ...overrides,
  }
}

describe('IntentConfirmationCard', () => {
  let onConfirm: ReturnType<typeof vi.fn>
  let onRephrase: ReturnType<typeof vi.fn>
  let onExpired: ReturnType<typeof vi.fn>

  beforeEach(() => {
    onConfirm = vi.fn().mockResolvedValue(undefined)
    onRephrase = vi.fn()
    onExpired = vi.fn()
  })

  it('renders intent_summary text', () => {
    render(
      <IntentConfirmationCard
        confirmation={makeConfirmation()}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )
    expect(screen.getByText(/Create a VM in us-central1/)).toBeInTheDocument()
  })

  it('renders confirmation_summary key/value pairs', () => {
    render(
      <IntentConfirmationCard
        confirmation={makeConfirmation()}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )
    expect(screen.getByText('us-central1')).toBeInTheDocument()
    expect(screen.getByText('n2-standard-4')).toBeInTheDocument()
  })

  it('calls onConfirm when "Looks right, continue" is clicked', async () => {
    render(
      <IntentConfirmationCard
        confirmation={makeConfirmation()}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )
    fireEvent.click(screen.getByText(/Looks right, continue/))
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1))
  })

  it('calls onRephrase when "Rephrase" is clicked', () => {
    render(
      <IntentConfirmationCard
        confirmation={makeConfirmation()}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )
    fireEvent.click(screen.getByText('Rephrase'))
    expect(onRephrase).toHaveBeenCalledTimes(1)
  })

  it('renders null when cancelled=true', () => {
    const { container } = render(
      <IntentConfirmationCard
        confirmation={makeConfirmation({ cancelled: true })}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('disables buttons while confirming', async () => {
    let resolveConfirm!: () => void
    onConfirm.mockReturnValueOnce(new Promise<void>((res) => { resolveConfirm = res }))

    render(
      <IntentConfirmationCard
        confirmation={makeConfirmation()}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )

    fireEvent.click(screen.getByText(/Looks right, continue/))

    expect(screen.getByText(/Confirming/)).toBeDisabled()
    expect(screen.getByText('Rephrase')).toBeDisabled()

    resolveConfirm()
    await waitFor(() => expect(screen.getByText(/Looks right, continue/)).not.toBeDisabled())
  })

  it('shows expiry message and calls onExpired when countdown reaches zero', async () => {
    vi.useFakeTimers()
    const expiresAt = new Date(Date.now() + 1_000).toISOString()
    render(
      <IntentConfirmationCard
        confirmation={makeConfirmation({ expires_at: expiresAt })}
        onConfirm={onConfirm}
        onRephrase={onRephrase}
        onExpired={onExpired}
      />,
    )

    await act(async () => {
      vi.advanceTimersByTime(2_000)
    })

    vi.useRealTimers()

    expect(screen.getByText(/Confirmation window expired/)).toBeInTheDocument()
    expect(onExpired).toHaveBeenCalled()
  })
})
