import type { Flag } from '@/review/api'

/** A pending, grounded, high-severity falls flag; override any field. */
export function flagFixture(over: Partial<Flag> = {}): Flag {
  return {
    id: 'f1',
    source: 'llm',
    category: 'falls',
    severity: 'high',
    evidence: 'found on floor',
    confidence: 0.91,
    grounding_status: 'exact',
    grounding_score: 100,
    span_start: 24,
    span_end: 38,
    review_reasons: ['high_severity'],
    review_status: 'pending',
    ...over,
  }
}
