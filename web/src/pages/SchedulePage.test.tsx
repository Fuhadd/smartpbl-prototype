/** The schedule screen against a fake API: carers, map, timeline, reasons, trade-off, re-optimise. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Me } from '@/auth/auth'
import { fakeApi, json, ME } from '@/test/fakeApi'
import { renderRoute } from '@/test/renderRoute'
import { placesFixture, runFixture, tradeoffFixture } from '@/test/scheduleFixtures'

const MANAGER = { ...ME.coordinator, username: 'sam@demo.smartpbl', display_name: 'Sam R.', role: 'manager',
  permissions: ['audit.read', 'note.read', 'review.queue.read', 'schedule.read', 'workforce.read'] }

function backend({ latest = runFixture() as unknown, solve = (_body: unknown) => json(runFixture({ id: 'run-2' }), 201) } = {}) {
  return fakeApi({
    'GET /schedule/latest': () => (latest ? json(latest) : json({ detail: 'no schedule saved yet' }, 404)),
    'GET /schedule/run-1/map': () => json(placesFixture()),
    'GET /schedule/run-2/map': () => json(placesFixture()),
    'GET /schedule/tradeoff': () => json(tradeoffFixture()),
    'POST /schedule/solve': async (req) => solve(JSON.parse(await req.text())),
  })
}

describe('schedule', () => {
  it('lists carers with travel and continuity, and the unassigned visit with its window', async () => {
    backend()
    renderRoute('/schedule')
    const carers = await screen.findByRole('region', { name: 'Carers on shift' })
    const first = within(carers).getByRole('button', { name: /CR-0001/ })
    expect(first).toHaveTextContent('CR-00012 visits · 38 min travel50%')
    expect(first).toHaveAttribute('aria-pressed', 'true')
    expect(await within(carers).findByText('CL-0208 · 12:30–13:00')).toBeInTheDocument()
    expect(within(carers).getByText('No carer on shift at 12:30-13:00 has: medication')).toBeInTheDocument()
  })

  it('draws the map with numbered visits for pinned carers', async () => {
    backend()
    renderRoute('/schedule')
    const map = await screen.findByRole('region', { name: 'Route map' })
    await waitFor(() => expect(map.querySelectorAll('.smartpbl-marker').length).toBeGreaterThan(0))
    // 3 pinned carers: 3 starts + 4 of their visits, plus 1 unassigned. CR-0004 isn't drawn.
    expect(map.querySelectorAll('.smartpbl-marker')).toHaveLength(8)
    expect(within(map).getByText('Unassigned')).toBeInTheDocument()
  })

  it('explains the selected visit, with the next-best carer', async () => {
    backend()
    renderRoute('/schedule')
    await userEvent.click(await screen.findByRole('button', { name: /CR-0001 visit 2: CL-0091/ }))
    const visit = screen.getByRole('region', { name: 'CL-0091 · CR-0001' })
    expect(await within(visit).findByText('Window 09:30–10:15 · arrives 09:00')).toBeInTheDocument()
    expect(within(visit).getByText('WHY CR-0001 WAS ASSIGNED')).toBeInTheDocument()
    expect(within(visit).getByText("Client's preferred carer")).toBeInTheDocument()
    expect(within(visit).getByText(/Next best:/)).toHaveTextContent('Next best: CR-0003 · +22 min travel, new to this client')
  })

  it('pins a fourth carer in place of the least recently chosen', async () => {
    backend()
    renderRoute('/schedule')
    await userEvent.click(await screen.findByRole('button', { name: /^CR-0004/ }))
    const timeline = screen.getByRole('region', { name: 'Timeline' })
    expect(within(timeline).getByText('CR-0004')).toBeInTheDocument()
    expect(within(timeline).queryByText('CR-0003')).toBeNull() // CR-0003 was the oldest pick
  })

  it('previews a preset from the sweep before applying it', async () => {
    backend()
    renderRoute('/schedule')
    const trade = await screen.findByRole('region', { name: 'Optimise for' })
    expect(within(trade).getByRole('button', { name: 'Balanced' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(trade).getByText('+2.0 h')).toBeInTheDocument() // 716 - 597 min
    expect(within(trade).getByText('+26 pts')).toBeInTheDocument() // 54.3% - 28.7%
    await userEvent.click(within(trade).getByRole('button', { name: 'Continuity' }))
    expect(within(trade).getByText('+2.6 h')).toBeInTheDocument()
    expect(within(trade).getByText('The saved rota uses Balanced. Nothing changes until you apply.')).toBeInTheDocument()
    expect(within(trade).getByRole('img', { name: /continuity setting sits at 56 percent and 12.6 hours/ })).toBeInTheDocument()
  })

  it('re-optimises with the chosen weight and shows the new run', async () => {
    let body: unknown
    const api = backend({ solve: (b) => ((body = b), json(runFixture({ id: 'run-2', params: { continuity_weight_min: 30 } }), 201)) })
    renderRoute('/schedule')
    const trade = await screen.findByRole('region', { name: 'Optimise for' })
    await userEvent.click(within(trade).getByRole('button', { name: 'Continuity' }))
    await userEvent.click(within(trade).getByRole('button', { name: 'Apply and re-optimise' }))
    await waitFor(() => expect(body).toEqual({ continuity_weight_min: 30, time_limit_s: 10 }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/schedule/run-2/map')).toBe(true))
    // The run view remounts for the new run, so look the panel up again.
    const after = screen.getByRole('region', { name: 'Optimise for' })
    expect(within(after).getByRole('button', { name: 'Continuity' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(after).queryByText(/Nothing changes until you apply/)).toBeNull()
  })

  it("shows the States sheet's error when a solve fails, and returns to the saved rota", async () => {
    backend({ solve: () => json({ detail: 'solver timed out' }, 500) })
    renderRoute('/schedule')
    await userEvent.click(await screen.findByRole('button', { name: 'Re-optimise' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Couldn't re-optimise the schedule")
    expect(alert).toHaveTextContent('Your last saved rota is still in place')
    expect(within(alert).getByText('Reference: req_8f2c41')).toBeInTheDocument()
    await userEvent.click(within(alert).getByRole('button', { name: 'View saved rota' }))
    expect(await screen.findByRole('region', { name: 'Carers on shift' })).toBeInTheDocument()
  })

  it('offers the first solve when nothing is saved', async () => {
    backend({ latest: null })
    renderRoute('/schedule')
    expect(await screen.findByRole('heading', { name: 'No rota saved yet' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Optimise the day' })).toBeEnabled()
  })

  it('lets care managers review but not re-optimise', async () => {
    backend()
    renderRoute('/schedule', MANAGER as unknown as Me)
    const trade = await screen.findByRole('region', { name: 'Optimise for' })
    expect(within(trade).queryByRole('button', { name: 'Apply and re-optimise' })).toBeNull()
    expect(within(trade).getByText(/Coordinators re-optimise the rota/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Re-optimise' })).toBeNull()
  })

  it('switches to a timeline of every carer', async () => {
    backend()
    renderRoute('/schedule')
    await userEvent.click(await screen.findByRole('button', { name: 'Timeline' }))
    expect(screen.queryByRole('region', { name: 'Route map' })).toBeNull()
    expect(within(screen.getByRole('region', { name: 'Timeline' })).getByText('CR-0004')).toBeInTheDocument()
  })
})
