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

/** An overview summary shaped like the design's day (Main.dc.html); override any section. */
export function overviewFixture(over: Record<string, unknown> = {}) {
  return {
    generated_at: '2026-11-07T09:00:00Z',
    review: {
      awaiting_flags: 6,
      awaiting_high: 2,
      notes_waiting: 4,
      attention: [
        { note_id: 'n1', client_ref: 'CL-0142', visit_time: '2026-11-07T08:47:00Z', severity: 'high', category: 'falls',
          evidence: 'found on bedroom floor, unable to get up' },
        { note_id: 'n2', client_ref: 'CL-0077', visit_time: '2026-11-07T07:52:00Z', severity: 'high', category: 'safeguarding',
          evidence: 'unexplained bruising noted on left forearm' },
        { note_id: 'n3', client_ref: 'CL-0315', visit_time: '2026-11-06T18:30:00Z', severity: 'medium', category: 'medication',
          evidence: "evening dose missing from yesterday's note" },
      ],
    },
    flags_by_category: {
      window_days: 7,
      counts: [
        { category: 'nutrition_hydration', count: 14 },
        { category: 'falls', count: 7 },
      ],
    },
    pipeline: { window_days: 7, extractions: 120, schema_valid_rate: 0.991, grounded_rate: 0.97, median_latency_ms: 3100,
      model_name: 'llama3.1:8b' },
    schedule: {
      run_id: 'r1', created_at: '2026-11-07T06:00:00Z', scenario_name: 'birmingham-day', preset: 'balanced',
      visits: 148, served: 145, unassigned: 3, carers_on_shift: 31, travel_h: 41.2, familiar_pct: 0.78,
      baseline: { solver: 'greedy', travel_h: 44.3, familiar_pct: 0.72, served: 140 },
      first_unassigned: { visit_id: 'V-0208', client_ref: 'CL-0208', detail: 'No carer on shift at 12:30-13:00 has: medication' },
    },
    workforce: { elevated: 4, total: 31, check_in: { carer_ref: 'WF-0461', factor_label: 'Weekly travel', factor_value: '6.2 h' } },
    ...over,
  }
}
