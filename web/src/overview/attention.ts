/**
 * "Needs attention" rows (Main.dc.html), built from the overview summary. Order: the
 * high-severity notes, then one unassigned visit, then the other notes, then one
 * supportive check-in. Everything is a link to the screen where it is acted on.
 */
import type { Category, Severity } from '@/review/categories'
import { clockTime } from '@/review/format'

import type { Overview } from './api'

export type AttentionTone = Severity | 'schedule' | 'workforce'
export type AttentionIcon = Category | 'extraction_failed' | 'unassigned' | 'check_in'

export type AttentionRow = {
  key: string
  to: string
  icon: AttentionIcon
  tone: AttentionTone
  title: string
  detail: string
  badge: string
}

const MAX_NOTES = 4
const MAX_HIGH_BEFORE_SCHEDULE = 3

const TITLE: Record<Category, string> = {
  falls: 'Fall reported',
  medication: 'Medication issue',
  nutrition_hydration: 'Nutrition concern',
  skin_integrity: 'Skin integrity concern',
  mood_behaviour: 'Change in mood',
  safeguarding: 'Safeguarding concern',
  missed_late_visit: 'Missed or late visit',
}
const SEVERITY_BADGE: Record<Severity, string> = { high: 'High', medium: 'Medium', low: 'Low' }

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export function attentionRows(o: Overview): AttentionRow[] {
  const notes: AttentionRow[] = o.review.attention.map((n) => ({
    key: `note-${n.note_id}`,
    to: `/review/${n.note_id}`,
    icon: n.category ?? 'extraction_failed',
    tone: n.severity,
    title: `${n.category ? TITLE[n.category] : 'AI extraction failed'} · ${n.client_ref}`,
    detail: `${n.evidence ? sentence(n.evidence) : 'Rules baseline only, needs a person'} · ${clockTime(n.visit_time)}`,
    badge: SEVERITY_BADGE[n.severity],
  }))
  const high = notes.filter((n) => n.tone === 'high').slice(0, MAX_HIGH_BEFORE_SCHEDULE)
  const rest = notes.filter((n) => !high.includes(n)).slice(0, Math.max(0, MAX_NOTES - high.length))

  const rows = [...high]
  const visit = o.schedule?.first_unassigned
  if (visit)
    rows.push({
      key: `visit-${visit.visit_id}`,
      to: '/schedule',
      icon: 'unassigned',
      tone: 'schedule',
      title: `Visit unassigned · ${visit.client_ref}`,
      detail: visit.detail,
      badge: 'Schedule',
    })
  rows.push(...rest)
  const check = o.workforce?.check_in
  if (check)
    rows.push({
      key: `carer-${check.carer_ref}`,
      to: `/workforce/${check.carer_ref}`,
      icon: 'check_in',
      tone: 'workforce',
      title: `Support check-in suggested · ${check.carer_ref}`,
      detail: `${check.factor_label}: ${check.factor_value}`,
      badge: 'Workforce',
    })
  return rows
}

/** "−3.1 h vs greedy baseline", or null when the run has no comparison. */
export function delta(value: number, baseline: number | undefined, unit: 'h' | 'pts', lowerIsBetter: boolean) {
  if (baseline === undefined) return null
  const raw = unit === 'pts' ? Math.round((value - baseline) * 100) : Math.round((value - baseline) * 10) / 10
  if (raw === 0) return { text: 'Same as greedy baseline', better: false }
  const sign = raw > 0 ? '+' : '−' // a real minus sign, as in the design
  const amount = unit === 'pts' ? `${Math.abs(raw)} pts` : `${Math.abs(raw).toFixed(1)} h`
  return { text: `${sign}${amount} vs greedy baseline`, better: lowerIsBetter ? raw < 0 : raw > 0 }
}

export const percent = (rate: number | null | undefined): string =>
  rate === null || rate === undefined ? '—' : `${Math.round(rate * 100)}%`
