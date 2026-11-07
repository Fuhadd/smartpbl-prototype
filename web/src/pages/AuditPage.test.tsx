/** The audit screen against a fake API: tiles, filters, search, expandable rows, paging, export. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Me } from '@/auth/auth'
import { tokenStore } from '@/auth/tokens'
import { fakeApi, json, ME } from '@/test/fakeApi'
import { renderRoute } from '@/test/renderRoute'

const SUMMARY = { day: '2026-11-07', entries_today: 412, high_flags_today: 2, high_flags_reviewed: 2, human_overrides: 7,
  access_denied: 2 }

function entry(id: number, over: Record<string, unknown> = {}) {
  return {
    id, event_ids: [id], occurred_at: '2026-11-07T08:48:00Z', kind: 'ai_output',
    actor: { kind: 'system', name: 'System', role: null }, subject: 'CL-0142 · care note', note_id: 'n1',
    version: 'llama3.1:8b · prompt v2', result: '3 flags · routed to review', details: [], ...over,
  }
}

const DECISION = entry(9, {
  kind: 'human_decision', event_ids: [9, 10, 11], actor: { kind: 'user', name: 'Hannah K.', role: 'coordinator' },
  version: null, result: 'Approved · escalated',
  details: [
    { label: 'Decision', value: 'Approved 3 flags unchanged', secondary: 'Escalated to care manager (falls, high)', mono: false },
    { label: 'Input fingerprint', value: 'hmac-sha256:3f9a…c71e', secondary: 'Raw text not stored in the log', mono: true },
  ],
})

function backend(pages: Record<string, unknown>[] = [{ entries: [DECISION, entry(5)], next_before: null }]) {
  return fakeApi({
    'GET /audit/summary': () => json(SUMMARY),
    'GET /audit': (req) => {
      const before = new URL(req.url).searchParams.get('before')
      return json(before ? pages[1] : pages[0])
    },
    'GET /audit/export': () => new Response('time_utc,event\n', { headers: { 'content-type': 'text/csv' } }),
  })
}

/** Full URLs the page requested whose path starts with `prefix`. */
const urls = (api: ReturnType<typeof backend>, prefix: string) =>
  api.fetch.mock.calls
    .map(([r]) => (r instanceof Request ? r.url : String(r)))
    .filter((u) => {
      const url = new URL(u)
      return (url.pathname + url.search).startsWith(prefix)
    })

afterEach(() => vi.useRealTimers())

describe('audit log', () => {
  it("shows today's tiles and the append-only badge", async () => {
    backend()
    renderRoute('/audit')
    const today = await screen.findByRole('region', { name: 'Today' })
    await within(today).findByText('412')
    expect(within(today).getByText('100%')).toBeInTheDocument()
    expect(within(today).getByText('7')).toBeInTheDocument()
    expect(screen.getByText('Append-only')).toBeInTheDocument()
    expect(screen.getByText('Demo data · synthetic')).toBeInTheDocument()
  })

  it('expands a row into its detail tiles and the raw row ids', async () => {
    backend()
    renderRoute('/audit')
    const toggle = await screen.findByRole('button', { name: /Human decision: show details/ })
    expect(screen.getByText('Hannah K. · coordinator')).toBeInTheDocument()
    expect(screen.queryByText('Approved 3 flags unchanged')).toBeNull()
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Approved 3 flags unchanged')).toBeInTheDocument()
    expect(screen.getByText('hmac-sha256:3f9a…c71e')).toHaveClass('font-mono')
    expect(screen.getByText('#9 #10 #11')).toBeInTheDocument()
  })

  it('filters by kind and searches once the user stops typing', async () => {
    const api = backend()
    renderRoute('/audit')
    await screen.findByText('Approved · escalated')
    await userEvent.click(screen.getByRole('button', { name: 'Human decision' }))
    expect(screen.getByRole('button', { name: 'Human decision' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.type(screen.getByLabelText('Search the audit log'), 'CL-0142')
    await waitFor(() => expect(urls(api, '/audit?').some((u) => u.includes('q=CL-0142'))).toBe(true))
    expect(urls(api, '/audit?').at(-1)).toContain('kind=human_decision')
    expect(urls(api, '/audit?').filter((u) => u.includes('q=')).length).toBe(1) // debounced
  })

  it('loads older entries with the keyset cursor', async () => {
    const api = backend([
      { entries: [DECISION], next_before: 9 },
      { entries: [entry(3, { result: 'Older entry' })], next_before: null },
    ])
    renderRoute('/audit')
    await userEvent.click(await screen.findByRole('button', { name: 'Load older entries' }))
    expect(await screen.findByText('Older entry')).toBeInTheDocument()
    expect(urls(api, '/audit?').some((u) => u.includes('before=9'))).toBe(true)
    expect(screen.queryByRole('button', { name: 'Load older entries' })).toBeNull()
  })

  it('exports the filtered view as a CSV download, with the bearer token', async () => {
    tokenStore.set({ access: 'A1', refresh: 'R1' })
    const api = backend()
    const create = vi.fn(() => 'blob:x')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderRoute('/audit')
    await userEvent.click(await screen.findByRole('button', { name: 'Access' }))
    await userEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(urls(api, '/audit/export').some((u) => u.includes('kind=access'))).toBe(true)
    expect(api.calls.find((c) => c.path === '/audit/export')!.auth).toBe('Bearer A1')
  })

  it('says when nothing matches', async () => {
    backend([{ entries: [], next_before: null }])
    renderRoute('/audit')
    expect(await screen.findByText('No entries yet. Decisions and AI outputs appear here as they happen.')).toBeInTheDocument()
  })

  it('is refused for carers, and the server records the attempt', async () => {
    const api = fakeApi({ 'GET /audit/summary': () => json({ detail: 'insufficient permissions' }, 403) })
    renderRoute('/audit', ME.carer as unknown as Me)
    expect(await screen.findByText('This attempt was recorded in the audit log.')).toBeInTheDocument()
    expect(api.calls.map((c) => c.path)).toContain('/audit/summary')
  })
})
