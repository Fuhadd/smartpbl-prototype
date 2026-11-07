/** A small saved rota, its places and the sweep, shaped like the API's responses. */
function visit(carer: string, seq: number, id: string, client: string, startH: number, over: Record<string, unknown> = {}) {
  return {
    carer_ref: carer, sequence: seq, visit_id: id, client_ref: client,
    start_s: startH * 3600, end_s: startH * 3600 + 1800, travel_s: 540, familiarity: 'preferred',
    reasons: ['Has the required skills: medication', 'Drives 9 min from previous visit (CL-0001)', "Client's preferred carer"],
    alternative: { carer_ref: 'CR-0003', extra_travel_min: 22, familiarity: 'new' },
    ...over,
  }
}

export function runFixture(over: Record<string, unknown> = {}) {
  const routes = [
    { carer_ref: 'CR-0001', travel_min: 38, visits: [visit('CR-0001', 1, 'V-0001', 'CL-0001', 7), visit('CR-0001', 2, 'V-0002', 'CL-0091', 9, { familiarity: 'new' })] },
    { carer_ref: 'CR-0002', travel_min: 46, visits: [visit('CR-0002', 1, 'V-0003', 'CL-0003', 8)] },
    { carer_ref: 'CR-0003', travel_min: 41, visits: [visit('CR-0003', 1, 'V-0004', 'CL-0004', 10, { alternative: null })] },
    { carer_ref: 'CR-0004', travel_min: 52, visits: [visit('CR-0004', 1, 'V-0005', 'CL-0005', 11)] },
  ]
  return {
    id: 'run-1', created_at: '2026-11-07T06:00:00Z', scenario_name: 'birmingham-day-seed42', scenario_seed: 42,
    scenario_hash: 'x', solver: 'ortools-9.15', params: { continuity_weight_min: 15, time_limit_s: 10, two_phase: true },
    status: 'ROUTING_SUCCESS', objective: 1, travel_min: 177, wall_s: 20, matrix_backend: 'osrm:car:x',
    metrics: { visits: 6, served: 5, dropped: 1 }, routes,
    dropped: [{ visit_id: 'V-0208', client_ref: 'CL-0208', reason: 'no_eligible_carer', eligible_carers: [], time_critical: true,
      detail: 'No carer on shift at 12:30-13:00 has: medication' }],
    requested_by: 'hannah@demo.smartpbl', ...over,
  }
}

export function tradeoffFixture() {
  const p = (w: number, drive: number, fam: number, pareto = true) =>
    ({ weight_min: w, drive_min: drive, familiar_pct: fam, preferred_pct: fam / 2, dropped: 0, pareto })
  return {
    scenario_name: 'birmingham-day-seed42', matrix_backend: 'osrm', time_limit_s: 30, visits: 94,
    points: [p(0, 597, 0.287), p(15, 716, 0.543), p(30, 753, 0.564), p(45, 770, 0.543, false)],
    presets: { travel: 0, balanced: 15, continuity: 30 },
  }
}

export function placesFixture() {
  const at = (i: number) => ({ lat: 52.45 + i * 0.01, lon: -1.9 + i * 0.01 })
  return {
    scenario_name: 'birmingham-day-seed42',
    carers: ['CR-0001', 'CR-0002', 'CR-0003', 'CR-0004'].map((c, i) => ({
      carer_ref: c, start: at(i), starts_from_home: true, shift_start_min: 420, shift_end_min: 870 })),
    visits: ['V-0001', 'V-0002', 'V-0003', 'V-0004', 'V-0005', 'V-0208'].map((v, i) => ({
      visit_id: v, client_ref: v === 'V-0002' ? 'CL-0091' : `CL-000${i + 1}`, location: at(i + 4),
      window_start_min: v === 'V-0002' ? 570 : 750, window_end_min: v === 'V-0002' ? 615 : 780, duration_min: 30,
      time_critical: false, required_skills: ['medication'] })),
  }
}
