import { describe, expect, it } from 'vitest'

import { flagFixture } from '@/test/fixtures'

import { draftOf, toDecisions } from './decisions'
import { modelLine, noteTitle, queueTime, whyReview } from './format'
import { redactedTypes, segmentNote, sentenceCase } from './noteText'

const NOTE = 'Arrived 08:15. <PERSON> found on floor. Daughter on <PHONE_NUMBER> informed.'

describe('segmentNote', () => {
  it('highlights evidence by offset and turns placeholders into chips', () => {
    const pieces = segmentNote(NOTE, [{ start: 24, end: 38, category: 'falls' }])
    expect(pieces).toEqual([
      { kind: 'text', text: 'Arrived 08:15. ' },
      { kind: 'redacted', label: 'NAME' },
      { kind: 'text', text: ' ' },
      { kind: 'highlight', category: 'falls', pieces: [{ kind: 'text', text: 'found on floor' }] },
      { kind: 'text', text: '. Daughter on ' },
      { kind: 'redacted', label: 'PHONE' },
      { kind: 'text', text: ' informed.' },
    ])
  })

  it('drops overlapping and out-of-range spans instead of garbling the text', () => {
    const pieces = segmentNote('abcdefghij', [
      { start: 2, end: 6, category: 'falls' },
      { start: 4, end: 8, category: 'mood_behaviour' }, // overlaps the first
      { start: 8, end: 99, category: 'medication' }, // past the end
    ])
    const flat = JSON.stringify(pieces)
    expect(flat).not.toContain('mood_behaviour')
    expect(flat).not.toContain('medication')
    const text = pieces.map((p) => (p.kind === 'text' ? p.text : p.kind === 'highlight' ? 'cdef' : '')).join('')
    expect(text).toBe('abcdefghij')
  })

  it('counts redactions and names their types: "Name, phone"', () => {
    const { count, words } = redactedTypes(NOTE)
    expect(count).toBe(2)
    expect(sentenceCase(words)).toBe('Name, phone')
  })
})

describe('review copy', () => {
  it("explains routing in the design's words", () => {
    const why = whyReview([flagFixture()], false)
    expect(why.because).toEqual(['one flag is high severity (falls)'])
    expect(why.confidence).toBe('All flags passed the confidence threshold of 0.70.')
    const low = whyReview([flagFixture({ review_reasons: ['low_confidence'] })], false)
    expect(low.confidence).toBe('One flag is below the confidence threshold of 0.70.')
  })

  it("builds the design's headline from category and visit time", () => {
    expect(noteTitle('falls', new Date(2026, 10, 7, 8, 15).toISOString())).toBe('Fall reported during morning visit')
    expect(noteTitle('safeguarding', new Date(2026, 10, 7, 19, 0).toISOString())).toBe(
      'Safeguarding concern reported during evening visit',
    )
    expect(noteTitle(undefined, new Date(2026, 10, 7, 13, 0).toISOString())).toBe('Care note from afternoon visit')
  })

  it('formats the model line and queue times like the design', () => {
    expect(
      modelLine({
        source: 'llm', status: 'ok', model_name: 'llama3.1:8b', model_version: 'x', prompt_version: 'extraction/v3',
        attempts: 1, latency_ms: 2800, errors: [], extraction: null,
      }),
    ).toBe('llama3.1:8b · prompt v3 · 2.8 s')
    const now = new Date(2026, 10, 7, 12, 0)
    expect(queueTime(new Date(2026, 10, 7, 8, 47).toISOString(), now)).toBe('08:47')
    expect(queueTime(new Date(2026, 10, 6, 20, 0).toISOString(), now)).toBe('Yesterday')
    expect(queueTime(new Date(2026, 10, 5, 9, 0).toISOString(), now)).toBe('Thu')
    expect(queueTime(new Date(2026, 9, 20, 9, 0).toISOString(), now)).toBe('20 Oct')
  })
})

describe('toDecisions', () => {
  const a = flagFixture({ id: 'a' })
  const b = flagFixture({ id: 'b', category: 'medication', severity: 'medium', evidence: 'refused tablets' })

  it('approves unchanged flags, edits only changed fields, rejects marked ones', () => {
    const drafts = {
      a: { ...draftOf(a), severity: 'medium' as const },
      b: { ...draftOf(b), reject: true },
    }
    expect(toDecisions([a, b], drafts, false)).toEqual([
      { flag_id: 'a', action: 'edit', edit: { severity: 'medium' } },
      { flag_id: 'b', action: 'reject' },
    ])
    expect(toDecisions([a, b], {}, false).map((d) => d.action)).toEqual(['approve', 'approve'])
  })

  it('"Reject" rejects every pending flag, whatever was staged', () => {
    const drafts = { a: { ...draftOf(a), severity: 'low' as const } }
    expect(toDecisions([a, b], drafts, true).map((d) => d.action)).toEqual(['reject', 'reject'])
  })

  it('trims edited evidence and ignores whitespace-only changes', () => {
    expect(toDecisions([b], { b: { ...draftOf(b), evidence: '  refused tablets ' } }, false)[0]?.action).toBe('approve')
  })
})
