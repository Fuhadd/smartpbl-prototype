/** Audit log: docs/design/screens/Audit.dc.html. A read-only view of the append-only log. */
import { Lock, Search } from 'lucide-react'
import { useEffect, useState } from 'react'

import { ApiError } from '@/api/client'
import { DemoBadge } from '@/app/AppShell'
import { AuditTable } from '@/audit/AuditTable'
import { downloadAuditCsv, useAuditSummary, useAuditTimeline, type EntryFilter } from '@/audit/api'
import { FILTERS, reviewedShare } from '@/audit/format'
import { ErrorState } from '@/components/states/States'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const SEARCH_DEBOUNCE_MS = 300

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return debounced
}

function SummaryTile({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-[20px] bg-surface px-5 py-[18px]">
      <span className="text-[13px] text-muted-foreground">{label}</span>
      <span className="text-[28px] font-bold">{value}</span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  )
}

function Summary() {
  const s = useAuditSummary()
  if (s.isPending)
    return (
      <section aria-label="Today" aria-busy="true" className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[104px] rounded-[20px] bg-surface" />
        ))}
      </section>
    )
  const d = s.data
  return (
    <section aria-label="Today" className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
      <SummaryTile label="Entries today" value={d ? d.entries_today : '—'} />
      <SummaryTile
        label="AI outputs reviewed by a person"
        value={d ? reviewedShare(d.high_flags_today, d.high_flags_reviewed) : '—'}
        note={d && d.high_flags_today === 0 ? 'no high-severity flags today' : 'of high-severity flags'}
      />
      <SummaryTile label="Human overrides" value={d ? d.human_overrides : '—'} note="edits or rejections" />
      <SummaryTile label="Access denied" value={d ? d.access_denied : '—'} note="blocked by role" />
    </section>
  )
}

export function AuditPage() {
  const [kind, setKind] = useState<EntryFilter>('all')
  const [search, setSearch] = useState('')
  const q = useDebounced(search.trim(), SEARCH_DEBOUNCE_MS)
  const timeline = useAuditTimeline(kind, q)
  const [now] = useState(() => new Date())
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const entries = timeline.data?.pages.flatMap((p) => p.entries) ?? []

  async function exportCsv() {
    setExporting(true)
    setExportError(null)
    try {
      await downloadAuditCsv(kind, q)
    } catch (e) {
      setExportError(e instanceof ApiError && e.reference ? `Export failed. Reference: ${e.reference}` : 'Export failed.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <main className="px-8 pt-6 pb-10 max-sm:px-4">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3.5">
            <h1 className="m-0 text-[28px] font-bold tracking-[-0.02em]">Audit log</h1>
            <span className="flex items-center gap-1.5 rounded-full border border-success-border bg-success-bg px-2.5 py-[3px] text-xs font-semibold text-success">
              <Lock size={13} strokeWidth={2} aria-hidden="true" />
              Append-only
            </span>
            <DemoBadge />
          </div>
          <div className="flex flex-col items-end gap-1">
            <Button type="button" variant="outline" size="pill" className="h-11 cursor-pointer" disabled={exporting} onClick={exportCsv}>
              {exporting ? 'Exporting…' : 'Export CSV'}
            </Button>
            {exportError && (
              <span role="alert" className="text-xs text-high">
                {exportError}
              </span>
            )}
          </div>
        </header>

        <Summary />

        <section aria-label="Filters" className="flex flex-wrap items-center gap-2.5">
          <label className="flex h-[42px] max-w-[360px] flex-[1_1_260px] items-center gap-2 rounded-full border border-border bg-surface px-4 text-muted-foreground">
            <Search size={18} strokeWidth={1.75} aria-hidden="true" />
            <span className="sr-only">Search the audit log</span>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              maxLength={100}
              placeholder="Search by client, user or note ID"
              className="w-full border-0 bg-transparent text-sm text-text outline-none"
            />
          </label>
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-pressed={kind === f.value}
              onClick={() => setKind(f.value)}
              className={cn(
                'h-[38px] cursor-pointer rounded-full px-3.5 text-[13px] font-medium',
                kind === f.value ? 'border-0 bg-primary text-primary-foreground' : 'border border-border bg-surface hover:bg-surface-muted',
              )}
            >
              {f.label}
            </button>
          ))}
        </section>

        {timeline.isError ? (
          <div className="flex min-h-[320px]">
            <ErrorState
              title="Couldn't load the audit log"
              message="The log itself is safe: entries are append-only and nothing was changed. Try again in a moment."
              onRetry={() => timeline.refetch()}
              secondary={{ label: 'Back to overview', to: '/' }}
              reference={timeline.error instanceof ApiError ? timeline.error.reference : null}
            />
          </div>
        ) : (
          <section aria-label="Audit entries" aria-busy={timeline.isPending} className="overflow-x-auto rounded-[22px] bg-surface p-2">
            {timeline.isPending ? (
              <div className="flex flex-col gap-2 p-2">
                {[0, 1, 2, 3, 4].map((i) => (
                  <Skeleton key={i} className="h-11 rounded-xl" />
                ))}
              </div>
            ) : entries.length === 0 ? (
              <p className="m-0 p-8 text-center text-sm text-muted-foreground">
                {q || kind !== 'all' ? 'No entries match these filters.' : 'No entries yet. Decisions and AI outputs appear here as they happen.'}
              </p>
            ) : (
              <>
                <AuditTable entries={entries} now={now} />
                {timeline.hasNextPage && (
                  <div className="flex justify-center p-3">
                    <Button
                      type="button"
                      variant="outline"
                      size="pill"
                      className="cursor-pointer"
                      disabled={timeline.isFetchingNextPage}
                      onClick={() => timeline.fetchNextPage()}
                    >
                      {timeline.isFetchingNextPage ? 'Loading…' : 'Load older entries'}
                    </Button>
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </div>
    </main>
  )
}
