/** Copy for the review screen, derived from API data. */
import type { components } from '@/api/schema'

import { CATEGORY } from './categories'

type Flag = components['schemas']['FlagOut']
type Extraction = components['schemas']['ExtractionOut']

/** Mirrors app/nlp/route.py CONFIDENCE_THRESHOLD (shown in "Why this needs review"). */
export const CONFIDENCE_THRESHOLD = 0.7

const REASON_TEXT: Record<string, (flag: Flag) => string> = {
  high_severity: (f) => `high severity (${CATEGORY[f.category].short.toLowerCase()})`,
  safeguarding_policy: () => 'a safeguarding concern, which a person always reviews',
  fuzzy_evidence: () => 'evidence that only approximately matches the note',
  ungrounded_evidence: () => 'evidence that could not be found in the note',
  low_confidence: () => 'below the confidence threshold',
  baseline_only: () => 'found by the rules but not by the AI',
}

/** "Routed because one flag is high severity (falls)." plus the confidence sentence. */
export function whyReview(flags: Flag[], extractionFailed: boolean): { because: string[]; confidence: string } {
  const because: string[] = []
  if (extractionFailed) because.push('the AI extraction failed, so only the rules baseline ran')
  for (const reason of Object.keys(REASON_TEXT)) {
    const hits = flags.filter((f) => f.review_reasons.includes(reason))
    if (!hits.length || reason === 'low_confidence') continue
    const text = REASON_TEXT[reason]!(hits[0]!)
    because.push(hits.length === 1 ? `one flag is ${text}` : `${hits.length} flags are ${text}`)
  }
  const low = flags.filter((f) => f.review_reasons.includes('low_confidence')).length
  const threshold = CONFIDENCE_THRESHOLD.toFixed(2)
  const confidence =
    low === 0
      ? `All flags passed the confidence threshold of ${threshold}.`
      : `${low === 1 ? 'One flag is' : `${low} flags are`} below the confidence threshold of ${threshold}.`
  return { because, confidence }
}

/** "llama3.1:8b · prompt v3 · 2.8 s" */
export function modelLine(e: Extraction | undefined): string {
  if (!e) return ''
  const parts = [e.model_name ?? 'unknown model']
  if (e.prompt_version) parts.push(`prompt ${e.prompt_version.split('/').pop()}`)
  if (e.latency_ms != null) parts.push(`${(e.latency_ms / 1000).toFixed(1)} s`)
  return parts.join(' · ')
}

const MEDICATION: Record<string, string> = {
  taken: 'Administered · no issues',
  refused: 'Refused',
  missed: 'Missed',
  partial: 'Partly taken',
  not_mentioned: 'Not mentioned',
}
export const medicationText = (status: unknown): string =>
  typeof status === 'string' ? (MEDICATION[status] ?? status) : 'Not available'

const time = (d: Date) => d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

/** Queue timestamps as in the design: "08:47", "Yesterday", "Thu", then "7 Nov". */
export function queueTime(iso: string, now: Date): string {
  const d = new Date(iso)
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((day(now) - day(d)) / 86_400_000)
  if (days <= 0) return time(d)
  if (days === 1) return 'Yesterday'
  if (days < 7) return d.toLocaleDateString('en-GB', { weekday: 'short' })
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

/** "Sat 7 Nov, 08:15" */
export function visitTime(iso: string): string {
  const d = new Date(iso)
  const date = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  return `${date.replace(',', '')}, ${time(d)}`
}
export const clockTime = (iso: string): string => time(new Date(iso))

const REPORTED: Record<string, string> = {
  falls: 'Fall reported',
  medication: 'Medication issue reported',
  nutrition_hydration: 'Nutrition concern reported',
  skin_integrity: 'Skin integrity concern reported',
  mood_behaviour: 'Change in mood reported',
  safeguarding: 'Safeguarding concern reported',
  missed_late_visit: 'Missed or late visit reported',
}

/** "Fall reported during morning visit": a deterministic headline from the top flag and
 * the visit time (the model's free-text summary is too long for a title, and is AI text). */
export function noteTitle(topCategory: string | undefined, visitIso: string): string {
  const h = new Date(visitIso).getHours()
  const period = h < 12 ? 'morning' : h < 17 ? 'afternoon' : h < 21 ? 'evening' : 'night'
  if (!topCategory) return `Care note from ${period} visit`
  return `${REPORTED[topCategory] ?? 'Concern reported'} during ${period} visit`
}
