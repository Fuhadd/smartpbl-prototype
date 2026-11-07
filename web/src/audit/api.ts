/** Server state for the audit log screen. */
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { api, toApiError } from '@/api/client'
import type { components } from '@/api/schema'

export type AuditEntry = components['schemas']['AuditEntry']
export type EntryKind = components['schemas']['EntryKind']
export type EntryFilter = components['schemas']['EntryFilter']

const PAGE = 50

export function useAuditSummary() {
  return useQuery({
    queryKey: ['audit', 'summary'],
    queryFn: async () => {
      const r = await api.GET('/audit/summary')
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
  })
}

/** Keyset pages: each page's `next_before` is the cursor for the next (older) one. */
export function useAuditTimeline(kind: EntryFilter, q: string) {
  return useInfiniteQuery({
    queryKey: ['audit', 'timeline', kind, q],
    initialPageParam: undefined as number | undefined,
    queryFn: async ({ pageParam }) => {
      const query = { kind, limit: PAGE, ...(q ? { q } : {}), ...(pageParam ? { before: pageParam } : {}) }
      const r = await api.GET('/audit', { params: { query } })
      if (!r.data) throw await toApiError(r.response, r.error)
      return r.data
    },
    getNextPageParam: (last) => last.next_before ?? undefined,
  })
}

/** Download the filtered timeline as CSV. Fetched with the bearer token (a plain link
 * can't carry it), then handed to the browser as a file. */
export async function downloadAuditCsv(kind: EntryFilter, q: string): Promise<void> {
  const r = await api.GET('/audit/export', { params: { query: { kind, ...(q ? { q } : {}) } }, parseAs: 'blob' })
  if (!r.response.ok) throw await toApiError(r.response, r.error)
  const url = URL.createObjectURL(r.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `smartpbl-audit-${new Date().toISOString().slice(0, 16).replaceAll(/[-:T]/g, '')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
