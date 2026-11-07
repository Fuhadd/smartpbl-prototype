/** Pure logic for the schedule screen: carer stats, pinned route colours, timeline layout. */
import type { Assignment, CarerRoute, Run } from './api'

/** DESIGN.md route colours: they differ in lightness, not only hue. */
export const ROUTE_COLOURS = ['#4338CA', '#F97316', '#0D9488'] as const
/** Darker text tones for numbers on white markers (Schedule.dc.html). */
export const ROUTE_TEXT = ['#4338CA', '#C2410C', '#0F766E'] as const
export const IDLE_COLOUR = '#D4D4D8'
export const MAX_PINNED = ROUTE_COLOURS.length

export type CarerStats = {
  carerRef: string
  visits: number
  travelMin: number
  familiarPct: number // share of this carer's visits to a preferred or recent client
}

const FAMILIAR = new Set(['preferred', 'recent'])

export function carerStats(run: Run): CarerStats[] {
  return run.routes
    .filter((r) => r.visits.length > 0)
    .map((r) => ({
      carerRef: r.carer_ref,
      visits: r.visits.length,
      travelMin: Math.round(r.travel_min),
      familiarPct: r.visits.filter((v) => FAMILIAR.has(v.familiarity)).length / r.visits.length,
    }))
    .sort((a, b) => a.carerRef.localeCompare(b.carerRef))
}

/**
 * Up to three carers are drawn in colour at once (more routes on one map are unreadable).
 * Each keeps its colour slot while pinned; pinning a fourth replaces the least recently
 * chosen, so the carer you just clicked never changes colour under you.
 */
export type Pins = { slots: string[]; recent: string[] }

export function initialPins(refs: string[]): Pins {
  const slots = refs.slice(0, MAX_PINNED)
  return { slots, recent: [...slots] } // the first carer starts selected, so it is the most recent
}

export function pin(p: Pins, ref: string): Pins {
  const recent = [ref, ...p.recent.filter((r) => r !== ref)]
  if (p.slots.includes(ref)) return { slots: p.slots, recent }
  if (p.slots.length < MAX_PINNED) return { slots: [...p.slots, ref], recent }
  const evict = [...p.slots].sort((a, b) => recent.indexOf(b) - recent.indexOf(a))[0]!
  return { slots: p.slots.map((s) => (s === evict ? ref : s)), recent: recent.filter((r) => r !== evict) }
}

export function colourOf(p: Pins, ref: string): string | null {
  const i = p.slots.indexOf(ref)
  return i === -1 ? null : ROUTE_COLOURS[i]!
}

export function textColourOf(p: Pins, ref: string): string {
  const i = p.slots.indexOf(ref)
  return i === -1 ? '#52525B' : ROUTE_TEXT[i]!
}

/** "09:40" from seconds after midnight. */
export function hhmm(seconds: number): string {
  const m = Math.floor(seconds / 60)
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

/** "09:30–10:15" from minutes after midnight. */
export const windowText = (startMin: number, endMin: number): string => `${hhmm(startMin * 60)}–${hhmm(endMin * 60)}`

/** Whole-hour axis covering every visit in `routes`, and block positions as percentages. */
export function timelineScale(routes: CarerRoute[]) {
  const all = routes.flatMap((r) => r.visits)
  if (all.length === 0) return { hours: [] as number[], place: () => ({ left: 0, width: 0 }) }
  const first = Math.floor(Math.min(...all.map((v) => v.start_s)) / 3600)
  const last = Math.ceil(Math.max(...all.map((v) => v.end_s)) / 3600)
  const span = Math.max(1, last - first) * 3600
  const hours = Array.from({ length: last - first }, (_, i) => first + i)
  const place = (v: Assignment) => ({
    left: ((v.start_s - first * 3600) / span) * 100,
    width: Math.max(0.6, ((v.end_s - v.start_s) / span) * 100),
  })
  return { hours, place }
}

/** "Next best: CR-0003 · +22 min travel, new to this client" */
export function nextBestText(a: Assignment): { carer: string; rest: string } | null {
  const alt = a.alternative
  if (!alt) return null
  const travel =
    alt.extra_travel_min === 0
      ? 'same travel'
      : `${alt.extra_travel_min > 0 ? '+' : '−'}${Math.abs(alt.extra_travel_min)} min travel`
  const fam = { preferred: "the client's preferred carer", recent: 'visited recently', new: 'new to this client' }[
    alt.familiarity
  ]
  return { carer: alt.carer_ref, rest: `${travel}, ${fam ?? alt.familiarity}` }
}

export const PRESET_LABEL = { travel: 'Travel', balanced: 'Balanced', continuity: 'Continuity', custom: 'Custom' } as const
export const PRESETS = ['travel', 'balanced', 'continuity'] as const
export type NamedPreset = (typeof PRESETS)[number]

/** The run's own preset, from the weight it was solved with. */
export function runPreset(run: Run, presets: Record<string, number>): NamedPreset | 'custom' {
  const w = (run.params as { continuity_weight_min?: number }).continuity_weight_min
  return PRESETS.find((p) => presets[p] === w) ?? 'custom'
}

export const SOLVE_HINT =
  'Re-optimising the day: OR-Tools first fixes which visits can be served, then trades travel for continuity. This takes up to 20 seconds; the saved rota stays in place until it finishes.'
