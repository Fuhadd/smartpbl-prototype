/** Copy for the audit table. */
import type { AuditEntry, EntryFilter, EntryKind } from './api'

export const FILTERS: { value: EntryFilter; label: string }[] = [
  { value: 'all', label: 'All events' },
  { value: 'ai_output', label: 'AI output' },
  { value: 'human_decision', label: 'Human decision' },
  { value: 'schedule_run', label: 'Schedule run' },
  { value: 'access', label: 'Access' },
]

/** Chip label and colours per entry kind (Audit.dc.html). */
export const KIND: Record<EntryKind, { label: string; className: string }> = {
  ai_output: { label: 'AI output', className: 'bg-ai-bg-strong text-ai-text' },
  access_denied: { label: 'Access denied', className: 'bg-high-bg text-high' },
  schedule_run: { label: 'Schedule run', className: 'bg-schedule-bg text-schedule' },
  human_decision: { label: 'Human decision', className: 'bg-primary text-primary-foreground' },
  note_submitted: { label: 'Note submitted', className: 'bg-bg text-soft' },
  security_alert: { label: 'Security alert', className: 'bg-high-bg text-high' },
}

const ROLE_WORD = { coordinator: 'coordinator', manager: 'care manager', carer: 'carer' } as const

/** "Hannah K. · coordinator", "System" */
export const actorText = (a: AuditEntry['actor']): string => (a.role ? `${a.name} · ${ROLE_WORD[a.role]}` : a.name)

/** "10:12" today, "6 Nov 14:02" before. */
export function entryTime(iso: string, now: Date): string {
  const d = new Date(iso)
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  if (d.toDateString() === now.toDateString()) return time
  return `${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} ${time}`
}

/** "100%" of high-severity flags decided by a person today, or "—" with none. */
export function reviewedShare(total: number, reviewed: number): string {
  return total === 0 ? '—' : `${Math.round((reviewed / total) * 100)}%`
}
