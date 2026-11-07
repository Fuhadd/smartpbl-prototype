/**
 * The audit table (Audit.dc.html). Each row expands into detail tiles. The expansion is
 * the WAI-ARIA disclosure pattern (a button with aria-expanded/aria-controls), which is
 * what shadcn's Collapsible implements; it is written out here because a Collapsible root
 * renders a <div>, and a <div> can't wrap the two <tr>s of a table row and its details.
 */
import { ChevronDown } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link } from 'react-router'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

import type { AuditEntry } from './api'
import { actorText, entryTime, KIND } from './format'

export function AuditTable({ entries, now }: { entries: AuditEntry[]; now: Date }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const toggle = (id: number) =>
    setOpen((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <Table className="min-w-[900px]">
      <TableHeader>
        <TableRow>
          {['Time', 'Event', 'Actor', 'Subject', 'Version', 'Result'].map((h) => (
            <TableHead key={h} scope="col">
              {h}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((e) => {
          const expanded = open.has(e.id)
          const kind = KIND[e.kind]
          const detailsId = `audit-details-${e.id}`
          const strong = expanded ? 'font-semibold' : undefined
          return (
            <Fragment key={e.id}>
              <TableRow
                onClick={() => toggle(e.id)}
                className={cn('cursor-pointer border-t border-track', expanded ? 'bg-surface-muted' : 'hover:bg-surface-muted')}
              >
                <TableCell className="tabular-nums">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-controls={detailsId}
                    aria-label={`${entryTime(e.occurred_at, now)} ${kind.label}: ${expanded ? 'hide' : 'show'} details`}
                    onClick={(ev) => {
                      ev.stopPropagation()
                      toggle(e.id)
                    }}
                    className={cn('flex cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 text-left tabular-nums', strong)}
                  >
                    {entryTime(e.occurred_at, now)}
                    <ChevronDown
                      size={14}
                      strokeWidth={1.75}
                      aria-hidden="true"
                      className={cn('text-muted-foreground transition-transform', expanded && 'rotate-180')}
                    />
                  </button>
                </TableCell>
                <TableCell>
                  <span className={cn('rounded-[6px] px-2 py-[3px] text-xs font-semibold whitespace-nowrap', kind.className)}>
                    {kind.label}
                  </span>
                </TableCell>
                <TableCell className={strong}>{actorText(e.actor)}</TableCell>
                <TableCell className={strong}>
                  {e.note_id && e.kind !== 'access_denied' ? (
                    <Link to={`/review/${e.note_id}`} onClick={(ev) => ev.stopPropagation()} className="hover:underline">
                      {e.subject}
                    </Link>
                  ) : (
                    e.subject
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{e.version ?? '—'}</TableCell>
                <TableCell className={strong}>{e.result}</TableCell>
              </TableRow>
              {expanded && (
                <TableRow className="bg-surface-muted">
                  <TableCell colSpan={6} className="px-3.5 pt-0 pb-4">
                    <div
                      id={detailsId}
                      className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3.5 rounded-[14px] border border-border bg-surface p-4 text-[13px]"
                    >
                      {e.details.map((d) => (
                        <div key={d.label} className="flex flex-col gap-1">
                          <span className="text-muted-foreground">{d.label}</span>
                          <span className={d.mono ? 'font-mono' : 'font-semibold'}>{d.value}</span>
                          {d.secondary && (
                            <span className={d.mono ? 'text-muted-foreground' : undefined}>{d.secondary}</span>
                          )}
                        </div>
                      ))}
                      <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground">Raw log rows</span>
                        <span className="font-mono">{e.event_ids.map((i) => `#${i}`).join(' ')}</span>
                        <span className="text-muted-foreground">Append-only; never edited</span>
                      </div>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
