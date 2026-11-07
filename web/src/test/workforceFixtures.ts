/** A small scored workforce and one explanation, shaped like the API's responses. */
const MODEL = { name: 'attrition-hgb', version: 'abc123def456', synthetic: true }
const NOTICE = 'Supportive use only. A higher score suggests where to offer help with working conditions.'

function factor(feature: string, label: string, value: string, team: string, points: number, support: string | null = null, lever = true) {
  return {
    feature, label, value, team_value: team, points, log_odds: points / 20,
    // As the API: a zero contribution counts as "lowers", and only raising factors carry support.
    direction: points > 0 ? 'raises' : 'lowers', provider_can_change: lever, support: points > 0 ? support : null,
  }
}

export function riskListFixture() {
  const carers = [
    { carer_ref: 'WF-0461', rank: 1, risk: 0.804, support_priority: true, band: 'elevated' },
    { carer_ref: 'WF-0102', rank: 2, risk: 0.41, support_priority: false, band: 'moderate' },
    { carer_ref: 'WF-0007', rank: 3, risk: 0.12, support_priority: false, band: 'low' },
  ].map((c) => ({ ...c, top_factors: [] }))
  return { model: MODEL, use_notice: NOTICE, average_risk: 0.3, support_share: 0.2, total: 3, carers }
}

export function explanationFixture(over: Record<string, unknown> = {}) {
  return {
    model: MODEL, use_notice: NOTICE, carer_ref: 'WF-0461', rank: 1, of: 3, risk: 0.804,
    baseline_risk: 0.282, average_risk: 0.3, support_priority: true, band: 'elevated',
    factors: [
      factor('short_notice_changes_per_month', 'Short-notice rota changes', '5 a month', '1 a month', 31.9, 'give more rota notice and limit late changes'),
      factor('familiar_share', 'Visits to familiar clients', '21%', '54%', 6.4, 'build a regular round of the same clients'),
      factor('drive_min_per_shift', 'Driving per shift', '61 min', '40 min', 4.4, 'review round geography to cut driving'),
      factor('zero_hours', 'Zero-hours contract', 'yes', '39% of team', 4.4, 'discuss a guaranteed-hours contract'),
      factor('weekly_paid_hours', 'Paid hours a week', '26.9 h', '16.4 h', 3.7, 'check hours match what the carer wants'),
      factor('split_shift_share', 'Shifts with a 90+ min gap', '20%', '66%', -2.4),
      factor('tenure_months', 'Time with the provider', '15 months', '24 months', 0.6, 'check induction, buddying and early supervision', false),
      factor('shifts_per_week', 'Shifts per week', '5', '4', 0.0, 'check hours match what the carer wants'),
    ],
    suggested_support: [
      'give more rota notice and limit late changes',
      'build a regular round of the same clients',
      'review round geography to cut driving',
      'discuss a guaranteed-hours contract',
      'check hours match what the carer wants',
    ],
    caveats: ['Scores are probabilities from a model trained on synthetic data.'],
    ...over,
  }
}
