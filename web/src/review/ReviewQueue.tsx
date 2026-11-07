/** The left panel of Review.dc.html: queue count, severity filter, notes by priority. */
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

import type { QueueItem } from './api'
import type { Severity } from './categories'
import { queueTime } from './format'
import { FILTERS, queueTitle, type QueueFilter } from './queue'

const DOT: Record<Severity, string> = { high: 'bg-dot-high', medium: 'bg-dot-medium', low: 'bg-dot-low' }

export function ReviewQueue({
  items,
  total,
  filter,
  onFilter,
  currentId,
  now,
}: {
  items: QueueItem[]
  total: number
  filter: QueueFilter
  onFilter: (f: QueueFilter) => void
  currentId: string | undefined
  now: Date
}) {
  return (
    <aside
      aria-labelledby="queue"
      className="box-border flex max-w-[300px] min-w-0 flex-[1_1_260px] flex-col gap-3.5 border-r border-border bg-surface px-4 py-5 max-md:max-w-none"
    >
      <div className="flex items-center justify-between px-2">
        <h2 id="queue" className="m-0 text-[15px] font-semibold">
          Review queue
        </h2>
        <span className="rounded-full bg-bg px-2 py-0.5 text-xs font-semibold">{total}</span>
      </div>
      <div className="flex gap-1.5 px-2" role="group" aria-label="Filter by severity">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            aria-pressed={filter === f.key}
            onClick={() => onFilter(f.key)}
            className={cn(
              'h-8 cursor-pointer rounded-full px-3 text-[13px] font-medium',
              filter === f.key ? 'border-0 bg-primary text-primary-foreground' : 'border border-border bg-surface',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {items.map((item) => {
          const n = item.pending_flags.length
          return (
            <li key={item.note_id}>
              <Link
                to={`/review/${item.note_id}`}
                aria-current={item.note_id === currentId ? 'page' : undefined}
                className={cn('flex gap-2.5 rounded-[14px] p-3 hover:bg-surface-muted', item.note_id === currentId && 'bg-bg')}
              >
                <span
                  aria-hidden="true"
                  className={cn('mt-1.5 size-2 flex-[0_0_8px] rounded-full', DOT[item.priority])}
                />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm font-semibold">{queueTitle(item)}</span>
                  <span className="text-xs text-muted-foreground">
                    {item.carer_ref} · {queueTime(item.created_at, now)} · {n} {n === 1 ? 'flag' : 'flags'}
                  </span>
                  <span className="sr-only">{item.priority} priority</span>
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
