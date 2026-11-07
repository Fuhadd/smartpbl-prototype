/** The workforce screen against a fake API: list, explanation, SHAP rows, actions, model card. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Me } from '@/auth/auth'
import { fakeApi, json, ME } from '@/test/fakeApi'
import { renderRoute } from '@/test/renderRoute'
import { explanationFixture, riskListFixture } from '@/test/workforceFixtures'

function backend(explanation: () => Response = () => json(explanationFixture())) {
  return fakeApi({
    'GET /workforce/risk': () => json(riskListFixture()),
    'GET /workforce/WF-0461/explanation': explanation,
    'GET /workforce/WF-0102/explanation': () =>
      json(explanationFixture({ carer_ref: 'WF-0102', rank: 2, risk: 0.41, band: 'moderate', support_priority: false })),
  })
}

describe('workforce', () => {
  it('opens on the highest-ranked carer and asks for the whole list', async () => {
    const { calls } = backend()
    const router = renderRoute('/workforce')
    expect(await screen.findByRole('heading', { level: 1, name: 'WF-0461' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/workforce/WF-0461')
    const risk = calls.find((c) => c.path === '/workforce/risk')
    expect(risk).toBeDefined()
  })

  it('lists carers with their band as text, marking the open one', async () => {
    backend()
    renderRoute('/workforce/WF-0461')
    const list = await screen.findByRole('navigation', { name: 'Carers by risk' })
    const links = within(list).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(['WF-0461Elevated', 'WF-0102Moderate', 'WF-0007Low'])
    expect(links[0]).toHaveAttribute('aria-current', 'page')
  })

  it('shows the score, band, rank and team comparisons', async () => {
    backend()
    renderRoute('/workforce/WF-0461')
    const header = await screen.findByRole('region', { name: 'WF-0461' })
    expect(header).toHaveTextContent('15 months with the provider · Zero-hours contract · 5 shifts a week')
    expect(header).toHaveTextContent('Attrition risk80%')
    expect(header).toHaveTextContent('ElevatedRank 1 of 3')
    const signals = screen.getByRole('region', { name: 'Key signals' })
    expect(signals).toHaveTextContent('Driving per shift61 minAdds +4 pts · team 40 min')
    expect(signals).toHaveTextContent('Split shifts20%team 66%')
  })

  it('draws the SHAP rows that add up from the baseline, readable without the colours', async () => {
    backend()
    renderRoute('/workforce/WF-0461')
    const drivers = await screen.findByRole('region', { name: "What's driving this estimate" })
    expect(drivers).toHaveTextContent('Baseline 28% → WF-0461 80%')
    const rows = within(drivers).getAllByRole('listitem')
    expect(rows).toHaveLength(7)
    expect(rows[0]).toHaveTextContent('Short-notice rota changes 5 a month (team 1 a month), raises risk by 32 points')
    expect(rows[5]).toHaveTextContent('lowers risk by 2 points')
    expect(rows[6]).toHaveTextContent('2 other factors')
  })

  it('suggests supportive actions, linking route changes to the schedule', async () => {
    backend()
    renderRoute('/workforce/WF-0461')
    const actions = await screen.findByRole('region', { name: 'Suggested supportive actions' })
    expect(within(actions).getByText('Book a supportive check-in')).toBeInTheDocument()
    const links = within(actions).getAllByRole('link', { name: 'Open in schedule' })
    expect(links).toHaveLength(2) // familiar clients and driving
    expect(links[0]).toHaveAttribute('href', '/schedule')
    expect(screen.getByText(/never for performance or disciplinary decisions/)).toBeInTheDocument()
  })

  it('hides the schedule link from a role that cannot read the schedule', async () => {
    backend()
    const me = { ...ME.coordinator, permissions: ['workforce.read'] } as unknown as Me
    renderRoute('/workforce/WF-0461', me)
    const actions = await screen.findByRole('region', { name: 'Suggested supportive actions' })
    expect(within(actions).queryByRole('link', { name: 'Open in schedule' })).toBeNull()
  })

  it('moves to another carer from the list', async () => {
    backend()
    const router = renderRoute('/workforce/WF-0461')
    const list = await screen.findByRole('navigation', { name: 'Carers by risk' })
    await userEvent.click(within(list).getByRole('link', { name: /WF-0102/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'WF-0102' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/workforce/WF-0102')
    // No check-in card for a moderate band.
    expect(screen.queryByText('Book a supportive check-in')).toBeNull()
  })

  it('opens the model card with the version, notice and caveats from the API', async () => {
    backend()
    renderRoute('/workforce/WF-0461')
    const button = await screen.findByRole('button', { name: 'Model card' })
    await waitFor(() => expect(button).toBeEnabled())
    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const card = screen.getByRole('region', { name: 'Model card' })
    expect(card).toHaveTextContent('abc123def456')
    expect(card).toHaveTextContent('Scores are probabilities from a model trained on synthetic data.')
  })

  it('says when a carer is not in the current workforce', async () => {
    fakeApi({ 'GET /workforce/risk': () => json(riskListFixture()) })
    renderRoute('/workforce/WF-9999')
    expect(await screen.findByRole('heading', { name: 'Carer not found' })).toBeInTheDocument()
  })

  it('shows an error with the request reference when the explanation fails', async () => {
    backend(() => json({ detail: 'boom' }, 500))
    renderRoute('/workforce/WF-0461')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Couldn't load this explanation")
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
