/** The review screen against a fake API: queue, highlights, decisions, escalation. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'

import { routes } from '@/app/router'
import { AuthContext, type Me } from '@/auth/auth'
import { fakeApi, json, ME } from '@/test/fakeApi'
import { flagFixture } from '@/test/fixtures'

const NOTE_TEXT = 'Arrived 08:15. <PERSON> found on floor, unable to get up. Refused breakfast. Daughter on <PHONE_NUMBER> informed.'
const at = (quote: string) => ({ span_start: NOTE_TEXT.indexOf(quote), span_end: NOTE_TEXT.indexOf(quote) + quote.length })

function note(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    external_id: id,
    client_ref: id === 'n1' ? 'CL-0142' : 'CL-0077',
    carer_ref: 'CR-0007',
    visit_time: '2026-11-07T08:15:00Z',
    redacted_text: NOTE_TEXT,
    review_required: true,
    created_at: '2026-11-07T08:47:00Z',
    escalated_at: null as string | null,
    escalated_by: null as string | null,
    flags: [
      flagFixture({ id: `${id}-falls`, evidence: 'found on floor, unable to get up', ...at('found on floor, unable to get up') }),
      flagFixture({
        id: `${id}-food`, category: 'nutrition_hydration', severity: 'medium', evidence: 'Refused breakfast',
        ...at('Refused breakfast'), confidence: 0.78, review_reasons: ['low_confidence'],
      }),
    ],
    extractions: [
      { source: 'llm', status: 'ok', model_name: 'llama3.1:8b', model_version: 'x', prompt_version: 'extraction/v2',
        attempts: 1, latency_ms: 2800, errors: [],
        extraction: { summary: 'Fall reported during morning visit', medication_status: 'taken', follow_up_required: true } },
      { source: 'baseline', status: 'ok', model_name: 'rules', model_version: null, prompt_version: null,
        attempts: 1, latency_ms: 1, errors: [], extraction: null },
    ],
    ...over,
  }
}

function queueItem(n: ReturnType<typeof note>) {
  return {
    note_id: n.id, external_id: n.id, client_ref: n.client_ref, carer_ref: n.carer_ref, visit_time: n.visit_time,
    created_at: n.created_at, redacted_text: n.redacted_text, extraction_failed: false, urgent: false, priority: 'high',
    pending_flags: n.flags,
  }
}

function setup(path: string, { queue = [note('n1'), note('n2')], me = ME.coordinator as unknown as Me } = {}) {
  const notes = Object.fromEntries(queue.map((n) => [n.id, n]))
  const api = fakeApi({
    'GET /review/queue': () => json(queue.filter((n) => n.review_required).map(queueItem)),
    'GET /notes/n1': () => json(notes.n1),
    'GET /notes/n2': () => json(notes.n2),
    'POST /review/notes/n1': async (req) => {
      const body = JSON.parse(await req.text())
      notes.n1 = { ...notes.n1, review_required: false, escalated_at: body.escalate ? '2026-11-07T09:05:00Z' : null }
      queue.splice(0, 1)
      return json({ note: notes.n1, decision_ids: ['d1', 'd2'], escalated: body.escalate })
    },
  })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const auth = { me, signIn: async () => me, signOut: async () => {}, can: (p: string) => me.permissions.includes(p as never) }
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthContext value={auth}>
        <RouterProvider router={router} />
      </AuthContext>
    </QueryClientProvider>,
  )
  return { api, router }
}

describe('review screen', () => {
  it('opens the first note in the queue', async () => {
    const { router } = setup('/review')
    await waitFor(() => expect(router.state.location.pathname).toBe('/review/n1'))
    expect(await screen.findByRole('heading', { name: /^Fall reported during/ })).toBeInTheDocument()
  })

  it('shows the note with highlighted evidence, redaction chips and the AI panel', async () => {
    setup('/review/n1')
    const original = (await screen.findByRole('heading', { name: 'ORIGINAL CARE NOTE' })).closest('section')!
    expect(within(original).getByText('found on floor, unable to get up').closest('mark')).not.toBeNull()
    expect(within(original).getByText('[NAME]')).toBeInTheDocument()
    expect(within(original).getByText('2 identifiers redacted')).toBeInTheDocument()
    expect(screen.getByText('llama3.1:8b · prompt v2 · 2.8 s')).toBeInTheDocument()
    expect(screen.getByText('Confidence 0.91')).toBeInTheDocument()
    expect(screen.getByText('Administered · no issues')).toBeInTheDocument()
    expect(screen.getByText(/Routed because/)).toHaveTextContent(
      'Routed because one flag is high severity (falls). One flag is below the confidence threshold of 0.70.',
    )
    expect(screen.getByText('Name, phone')).toBeInTheDocument()
    expect(screen.getByText('High risk')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'PBL FALLS PROTOCOL' })).toBeInTheDocument()
    // Severity is always text plus colour.
    expect(screen.getAllByText('High').length).toBeGreaterThan(0)
  })

  it("titles the note from its top flag and visit time, not the model's free text", async () => {
    const n = note('n1')
    n.extractions[0]!.extraction!.summary = 'Found <PERSON> on the floor.'
    setup('/review/n1', { queue: [n] })
    const h1 = await screen.findByRole('heading', { level: 1 })
    expect(h1.textContent).toMatch(/^Fall reported during (morning|afternoon|evening|night) visit$/)
    expect(document.body.textContent).not.toContain('<PERSON>')
  })

  it('approves every pending flag in one request, then moves to the next note', async () => {
    const { api, router } = setup('/review/n1')
    await userEvent.click(await screen.findByRole('button', { name: 'Approve and log decision' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/review/n2'))
    const call = api.calls.find((c) => c.method === 'POST' && c.path === '/review/notes/n1')!
    expect(JSON.parse(call.body)).toEqual({
      decisions: [
        { flag_id: 'n1-falls', action: 'approve' },
        { flag_id: 'n1-food', action: 'approve' },
      ],
      escalate: false,
    })
  })

  it('sends staged edits and rejections with the decision', async () => {
    const { api } = setup('/review/n1')
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const [severity] = screen.getAllByLabelText('Severity')
    await userEvent.selectOptions(severity!, 'medium')
    await userEvent.click(screen.getAllByRole('button', { name: 'Reject flag' })[1]!)
    await userEvent.click(screen.getByRole('button', { name: 'Approve extraction' }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/review/notes/n1')).toBe(true))
    const body = JSON.parse(api.calls.find((c) => c.path === '/review/notes/n1')!.body)
    expect(body.decisions).toEqual([
      { flag_id: 'n1-falls', action: 'edit', edit: { severity: 'medium' } },
      { flag_id: 'n1-food', action: 'reject' },
    ])
  })

  it('offers escalation only while a high-severity flag is kept', async () => {
    const { api } = setup('/review/n1')
    expect(await screen.findByRole('button', { name: 'Escalate to care manager' })).toBeInTheDocument()
    expect(screen.getByText('Required')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.selectOptions(screen.getAllByLabelText('Severity')[0]!, 'medium')
    expect(screen.queryByRole('button', { name: 'Escalate to care manager' })).toBeNull()
    await userEvent.selectOptions(screen.getAllByLabelText('Severity')[0]!, 'high')
    await userEvent.click(screen.getByRole('button', { name: 'Escalate to care manager' }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/review/notes/n1')).toBe(true))
    expect(JSON.parse(api.calls.find((c) => c.path === '/review/notes/n1')!.body).escalate).toBe(true)
  })

  it('explains a conflict when another reviewer got there first', async () => {
    setup('/review/n1')
    fakeApi({
      'GET /review/queue': () => json([queueItem(note('n1'))]),
      'GET /notes/n1': () => json(note('n1')),
      'POST /review/notes/n1': () => json({ detail: 'flag already reviewed (approved)' }, 409),
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Approve extraction' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Another reviewer has already decided this note. Reload to see the latest.',
    )
  })

  it('shows "All caught up" when nothing is waiting', async () => {
    setup('/review', { queue: [] })
    expect(await screen.findByRole('heading', { name: 'All caught up' })).toBeInTheDocument()
  })

  it('lets a care manager read the note but not decide it', async () => {
    const manager = {
      ...ME.coordinator, role: 'manager', display_name: 'Sam R.',
      permissions: ['audit.read', 'note.read', 'review.queue.read', 'schedule.read', 'workforce.read'],
    } as unknown as Me
    setup('/review/n1', { me: manager })
    expect(await screen.findByRole('heading', { name: /^Fall reported during/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve and log decision' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Approve extraction' })).toBeNull()
  })

  it('filters the queue by severity', async () => {
    setup('/review/n1', { queue: [note('n1'), note('n2')] })
    const queue = await screen.findByRole('complementary', { name: 'Review queue' })
    await waitFor(() => expect(within(queue).getAllByRole('link')).toHaveLength(2))
    await userEvent.click(within(queue).getByRole('button', { name: 'Medium' }))
    expect(within(queue).queryAllByRole('link')).toHaveLength(0)
  })
})
