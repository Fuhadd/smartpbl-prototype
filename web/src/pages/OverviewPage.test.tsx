/** The overview against a fake API: tiles, attention list, panels, empty and error states. */
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { fakeApi, json } from '@/test/fakeApi'
import { overviewFixture } from '@/test/fixtures'
import { renderRoute } from '@/test/renderRoute'

describe('overview', () => {
  it('shows today at a glance with links to each screen', async () => {
    fakeApi({ 'GET /overview': () => json(overviewFixture()) })
    renderRoute('/')
    const glance = await screen.findByRole('region', { name: 'Today at a glance' })
    const flags = within(glance).getByRole('link', { name: /Flags awaiting review/ })
    expect(flags).toHaveTextContent('Flags awaiting review62 high severity')
    expect(flags).toHaveAttribute('href', '/review')
    expect(within(glance).getByRole('link', { name: /Unassigned visits/ })).toHaveTextContent('3Re-optimise schedule')
    expect(within(glance).getByRole('link', { name: /Visits today/ })).toHaveTextContent('14831 carers on shift')
    expect(within(glance).getByRole('link', { name: /Carers at elevated risk/ })).toHaveAttribute('href', '/workforce')
  })

  it('lists what needs attention, each with text and colour severity', async () => {
    fakeApi({ 'GET /overview': () => json(overviewFixture()) })
    renderRoute('/')
    const panel = await screen.findByRole('region', { name: 'Needs attention' })
    const links = within(panel).getAllByRole('link').filter((a) => a.textContent !== 'See all')
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/review/n1', '/review/n2', '/schedule', '/review/n3', '/workforce/WF-0461'])
    expect(within(panel).getAllByText('High')).toHaveLength(2)
  })

  it('shows category bars, the schedule against the greedy baseline and pipeline health', async () => {
    fakeApi({ 'GET /overview': () => json(overviewFixture()) })
    renderRoute('/')
    expect(await screen.findByLabelText('Nutrition / hydration: 14')).toBeInTheDocument()
    const sched = screen.getByRole('region', { name: "Today's schedule" })
    expect(within(sched).getByText('Balanced')).toBeInTheDocument()
    expect(within(sched).getByText('41.2 h')).toBeInTheDocument()
    expect(within(sched).getByText('\u22123.1 h vs greedy baseline')).toBeInTheDocument()
    expect(within(sched).getByText('+6 pts vs greedy baseline')).toBeInTheDocument()
    const ai = screen.getByRole('region', { name: 'AI pipeline health' })
    expect(within(ai).getByText('99%')).toBeInTheDocument()
    expect(within(ai).getByText('3.1 s')).toBeInTheDocument()
    expect(within(ai).getByText('llama3.1:8b · local')).toBeInTheDocument()
  })

  it('says when there is no rota instead of showing zeros', async () => {
    fakeApi({ 'GET /overview': () => json(overviewFixture({ schedule: null })) })
    renderRoute('/')
    const sched = await screen.findByRole('region', { name: "Today's schedule" })
    expect(within(sched).getByText(/No rota saved yet/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Today at a glance' })).getAllByText('—')).toHaveLength(2)
  })

  it('offers a retry with the server reference when the summary fails', async () => {
    let fail = true
    fakeApi({ 'GET /overview': () => (fail ? json({ detail: 'boom' }, 500) : json(overviewFixture())) })
    renderRoute('/')
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the overview")
    expect(screen.getByText('Reference: req_8f2c41')).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('region', { name: 'Today at a glance' })).toBeInTheDocument()
  })
})
