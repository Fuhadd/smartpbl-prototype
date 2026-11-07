/** The four reusable states render docs/design/screens/States.dc.html's copy. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { greeting, longDate } from '@/lib/dates'

import { EmptyState, ErrorState, LoadingOverview } from './States'

const inRouter = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('states', () => {
  it('empty: review queue', () => {
    inRouter(<EmptyState />)
    expect(screen.getByRole('heading', { name: 'All caught up' })).toBeInTheDocument()
    expect(
      screen.getByText('No care notes are waiting for review. New flags appear here automatically.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View recent decisions' })).toHaveAttribute('href', '/audit')
  })

  it('loading: overview is announced, not just drawn', () => {
    const { container } = inRouter(<LoadingOverview />)
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.getByText('Loading overview')).toHaveClass('sr-only')
  })

  it('error: schedule, with retry and the request reference', async () => {
    const retry = vi.fn()
    inRouter(<ErrorState onRetry={retry} reference="req_8f2c41" />)
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't re-optimise the schedule")
    expect(screen.getByText(/Your last saved rota is still in place/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
    expect(screen.getByRole('link', { name: 'View saved rota' })).toHaveAttribute('href', '/schedule')
    expect(screen.getByText('Reference: req_8f2c41')).toBeInTheDocument()
  })
})

describe('overview greeting', () => {
  it("formats the date as the design does: 'Saturday, 7 November'", () => {
    const d = new Date(2026, 10, 7, 9, 0)
    expect(longDate(d)).toBe('Saturday, 7 November')
    expect(greeting(d)).toBe('Good morning')
    expect(greeting(new Date(2026, 10, 7, 14))).toBe('Good afternoon')
    expect(greeting(new Date(2026, 10, 7, 19))).toBe('Good evening')
  })
})
