/**
 * Split a redacted note into plain text, evidence highlights and redaction placeholders,
 * using the flags' character offsets into `redacted_text` (set by the API's grounding).
 */
import type { Category } from './categories'

export type Span = { start: number; end: number; category: Category }
export type Piece =
  | { kind: 'text'; text: string }
  | { kind: 'redacted'; label: string }
  | { kind: 'highlight'; category: Category; pieces: Piece[] }

/** Presidio entity -> the design's chip label ("[NAME]", "[PHONE]"). */
export const PLACEHOLDER_LABEL: Record<string, string> = {
  PERSON: 'NAME',
  PHONE_NUMBER: 'PHONE',
  UK_STREET_ADDRESS: 'ADDRESS',
  UK_POSTCODE: 'POSTCODE',
  LOCATION: 'PLACE',
  EMAIL_ADDRESS: 'EMAIL',
  UK_NHS: 'NHS NUMBER',
}

/** The words for the "Identifiers redacted before AI" check: "Name, phone, address". */
const PLACEHOLDER_WORD: Record<string, string> = {
  PERSON: 'name',
  PHONE_NUMBER: 'phone',
  UK_STREET_ADDRESS: 'address',
  UK_POSTCODE: 'postcode',
  LOCATION: 'place',
  EMAIL_ADDRESS: 'email',
  UK_NHS: 'NHS number',
}

const PLACEHOLDER = /<([A-Z_]+)>/g

function withPlaceholders(text: string): Piece[] {
  const out: Piece[] = []
  let last = 0
  for (const m of text.matchAll(PLACEHOLDER)) {
    const entity = m[1] ?? ''
    if (!(entity in PLACEHOLDER_LABEL)) continue // not ours: leave as text
    if (m.index > last) out.push({ kind: 'text', text: text.slice(last, m.index) })
    out.push({ kind: 'redacted', label: PLACEHOLDER_LABEL[entity] ?? entity })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) })
  return out
}

/** Highlights are applied first (offsets refer to the raw redacted string), then
 * placeholders inside every piece. Overlapping spans: the earlier one wins. */
export function segmentNote(text: string, spans: Span[]): Piece[] {
  const sorted = [...spans]
    .filter((s) => s.start >= 0 && s.end <= text.length && s.end > s.start)
    .sort((a, b) => a.start - b.start || b.end - a.end)
  const out: Piece[] = []
  let cursor = 0
  for (const s of sorted) {
    if (s.start < cursor) continue // overlaps a highlight already placed
    if (s.start > cursor) out.push(...withPlaceholders(text.slice(cursor, s.start)))
    out.push({ kind: 'highlight', category: s.category, pieces: withPlaceholders(text.slice(s.start, s.end)) })
    cursor = s.end
  }
  if (cursor < text.length) out.push(...withPlaceholders(text.slice(cursor)))
  return out
}

/** Entity types redacted in this note, in first-seen order. */
export function redactedTypes(text: string): { count: number; words: string[] } {
  const words: string[] = []
  let count = 0
  for (const m of text.matchAll(PLACEHOLDER)) {
    const word = PLACEHOLDER_WORD[m[1] ?? '']
    if (!word) continue
    count += 1
    if (!words.includes(word)) words.push(word)
  }
  return { count, words }
}

export function sentenceCase(words: string[]): string {
  const joined = words.join(', ')
  return joined.charAt(0).toUpperCase() + joined.slice(1)
}
