import { describe, expect, it } from 'vitest'

import { explanationFixture } from '@/test/workforceFixtures'

import type { Explanation } from './api'
import { barWidth, driverRows, profileLine, signedPoints, supportActions } from './model'

const e = explanationFixture() as unknown as Explanation

describe('workforce model', () => {
  it('formats points with a true minus and a decimal below one point', () => {
    expect(signedPoints(31.9)).toBe('+32')
    expect(signedPoints(-2.4)).toBe('−2')
    expect(signedPoints(0.6)).toBe('+0.6')
  })

  it('keeps the six largest factors and folds the rest so the rows still add up', () => {
    const rows = driverRows(e.factors)
    expect(rows.map((r) => r.key)).toEqual([
      'short_notice_changes_per_month', 'familiar_share', 'drive_min_per_shift', 'zero_hours',
      'weekly_paid_hours', 'split_shift_share', 'other',
    ])
    expect(rows.at(-1)).toMatchObject({ label: '2 other factors', team: null })
    const sum = (xs: { points: number }[]) => xs.reduce((s, x) => s + x.points, 0)
    expect(sum(rows)).toBeCloseTo(sum(e.factors))
  })

  it('scales bars so the largest fills 90%', () => {
    const rows = driverRows(e.factors)
    expect(barWidth(31.9, rows)).toBeCloseTo(90)
    expect(barWidth(-2.4, rows)).toBeCloseTo((2.4 / 31.9) * 90)
  })

  it('builds one supportive action per suggestion and a check-in only when elevated', () => {
    const actions = supportActions(e)
    expect(actions.map((a) => a.title)).toEqual([
      'Give more rota notice and limit late changes',
      'Build a regular round of the same clients',
      'Review round geography to cut driving',
      'Discuss a guaranteed-hours contract',
      'Check hours match what the carer wants',
      'Book a supportive check-in',
    ])
    expect(actions[2]).toMatchObject({ kind: 'route', schedule: true })
    expect(actions[0]).toMatchObject({ kind: 'rota', schedule: false })
    expect(actions[0]!.detail).toBe('Short-notice rota changes 5 a month (team 1 a month) adds +32 pts')
    // Shifts per week shares this support but contributes nothing, so it isn't named.
    expect(actions[4]!.detail).toBe('Paid hours a week 26.9 h (team 16.4 h) adds +4 pts')
    const moderate = supportActions({ ...e, band: 'moderate' })
    expect(moderate.some((a) => a.kind === 'check_in')).toBe(false)
  })

  it('describes the carer by tenure, contract and shifts, never by name', () => {
    expect(profileLine(e)).toBe('15 months with the provider · Zero-hours contract · 5 shifts a week')
  })
})
