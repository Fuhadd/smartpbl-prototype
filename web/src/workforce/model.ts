/** Pure view logic for the workforce screen: bands, SHAP rows, signals and support actions. */
import type { Band, Explanation, Factor } from './api'

export const BAND_LABEL: Record<Band, string> = { elevated: 'Elevated', moderate: 'Moderate', low: 'Low' }
export const BAND_BADGE: Record<Band, 'elevated' | 'medium' | 'success'> = {
  elevated: 'elevated',
  moderate: 'medium',
  low: 'success',
}

export const percent = (p: number) => `${Math.round(p * 100)}%`

/** "+14", "−5" (true minus sign), or one decimal below 1 point so small factors don't read as 0. */
export function signedPoints(points: number): string {
  const size = Math.abs(points)
  const shown = size >= 1 ? Math.round(size).toString() : size.toFixed(1)
  return `${points < 0 ? '−' : '+'}${shown}`
}

export type DriverRow = { key: string; label: string; team: string | null; points: number }

/** Bar rows shown before the rest fold into one "other factors" row. */
export const DRIVER_ROWS = 6

/**
 * The largest contributions by size, then everything else summed into one row, so the
 * chart still adds up from the baseline to the carer's score.
 */
export function driverRows(factors: Factor[], shown = DRIVER_ROWS): DriverRow[] {
  const sorted = [...factors].sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
  const rows: DriverRow[] = sorted.slice(0, shown).map((f) => ({
    key: f.feature,
    label: `${f.label} ${f.value}`,
    team: f.team_value,
    points: f.points,
  }))
  const rest = sorted.slice(shown)
  if (rest.length)
    rows.push({
      key: 'other',
      label: `${rest.length} other factors`,
      team: null,
      points: rest.reduce((s, f) => s + f.points, 0),
    })
  return rows
}

/** Bar length as a % of its half of the chart: the largest bar fills 90%, as in the design. */
export function barWidth(points: number, rows: DriverRow[]): number {
  const max = Math.max(...rows.map((r) => Math.abs(r.points)), 1e-9)
  return (Math.abs(points) / max) * 90
}

/** The four signal tiles (Workforce.dc.html "Key signals"): working conditions the rota sets. */
export const KEY_SIGNALS = [
  { feature: 'drive_min_per_shift', title: 'Driving per shift' },
  { feature: 'familiar_share', title: 'Familiar clients' },
  { feature: 'short_notice_changes_per_month', title: 'Short-notice changes' },
  { feature: 'split_shift_share', title: 'Split shifts' },
] as const

export function factorOf(e: Explanation, feature: string): Factor | undefined {
  return e.factors.find((f) => f.feature === feature)
}

/** Factors a coordinator would act on in the schedule screen. */
const SCHEDULE_FEATURES = new Set([
  'drive_min_per_shift',
  'visits_per_shift',
  'familiar_share',
  'gap_min_per_shift',
  'split_shift_share',
])

export type ActionKind = 'route' | 'rota' | 'clients' | 'contract' | 'development' | 'check_in'

export type SupportAction = {
  kind: ActionKind
  title: string
  detail: string
  /** Show "Open in schedule": the change is made in the schedule. */
  schedule: boolean
}

const KIND: Record<string, ActionKind> = {
  drive_min_per_shift: 'route',
  visits_per_shift: 'route',
  familiar_share: 'clients',
  short_notice_changes_per_month: 'rota',
  gap_min_per_shift: 'rota',
  split_shift_share: 'rota',
  late_shift: 'rota',
  shifts_per_week: 'contract',
  weekly_paid_hours: 'contract',
  zero_hours: 'contract',
  tenure_months: 'development',
  skills_count: 'development',
}

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/**
 * One card per suggested support (the API already keeps only levers that add at least
 * ~2 points), naming the factors behind it. Elevated carers also get the check-in the
 * model card recommends for the top 20%, worded as support, not performance.
 */
export function supportActions(e: Explanation): SupportAction[] {
  const actions: SupportAction[] = e.suggested_support.map((support) => {
    const behind = e.factors.filter((f) => f.support === support && f.direction === 'raises')
    const detail = behind
      .map((f) => `${f.label} ${f.value} (team ${f.team_value}) adds ${signedPoints(f.points)} pts`)
      .join('; ')
    return {
      kind: KIND[behind[0]?.feature ?? ''] ?? 'rota',
      title: sentence(support),
      detail,
      schedule: behind.some((f) => SCHEDULE_FEATURES.has(f.feature)),
    }
  })
  if (e.band === 'elevated')
    actions.push({
      kind: 'check_in',
      title: 'Book a supportive check-in',
      detail: 'A supervision conversation about workload, not a performance review',
      schedule: false,
    })
  return actions
}

/** "15 months with the provider · Zero-hours contract · 5 shifts a week". */
export function profileLine(e: Explanation): string {
  const tenure = factorOf(e, 'tenure_months')?.value
  const zero = factorOf(e, 'zero_hours')?.value
  const shifts = factorOf(e, 'shifts_per_week')?.value
  return [
    tenure && `${tenure} with the provider`,
    zero && (zero === 'yes' ? 'Zero-hours contract' : 'Guaranteed hours'),
    shifts && `${shifts} shifts a week`,
  ]
    .filter(Boolean)
    .join(' · ')
}
