import { describe, expect, it } from 'vitest'

import { overviewFixture } from '@/test/fixtures'

import type { Overview } from './api'
import { attentionRows, delta, percent } from './attention'

const overview = (over: Record<string, unknown> = {}) => overviewFixture(over) as unknown as Overview

describe('needs attention', () => {
  it('orders high notes, then the unassigned visit, then other notes, then a check-in', () => {
    const rows = attentionRows(overview())
    expect(rows.map((r) => r.badge)).toEqual(['High', 'High', 'Schedule', 'Medium', 'Workforce'])
    expect(rows[0]).toMatchObject({ title: 'Fall reported · CL-0142', to: '/review/n1' })
    expect(rows[0]!.detail).toMatch(/^Found on bedroom floor, unable to get up · \d\d:\d\d$/)
    expect(rows[2]).toMatchObject({ title: 'Visit unassigned · CL-0208', to: '/schedule' })
    expect(rows[4]).toMatchObject({ title: 'Support check-in suggested · WF-0461', detail: 'Weekly travel: 6.2 h' })
  })

  it('leaves out sections that have nothing to say', () => {
    const rows = attentionRows(overview({ schedule: null, workforce: null }))
    expect(rows.map((r) => r.badge)).toEqual(['High', 'High', 'Medium'])
  })

  it('names a failed extraction instead of inventing a category', () => {
    const o = overview()
    o.review.attention = [{ ...o.review.attention[0]!, category: null, evidence: null, severity: 'medium' }]
    expect(attentionRows(o)[1]!.title).toBe('AI extraction failed · CL-0142')
  })
})

describe('comparison with the greedy baseline', () => {
  it('uses a real minus sign and marks improvements', () => {
    expect(delta(41.2, 44.3, 'h', true)).toEqual({ text: '\u22123.1 h vs greedy baseline', better: true })
    expect(delta(0.78, 0.72, 'pts', false)).toEqual({ text: '+6 pts vs greedy baseline', better: true })
    expect(delta(46, 44, 'h', true)).toEqual({ text: '+2.0 h vs greedy baseline', better: false })
    expect(delta(0.7, undefined, 'pts', false)).toBeNull()
  })

  it('shows a dash rather than 0% when there is no data', () => {
    expect(percent(null)).toBe('—')
    expect(percent(0.991)).toBe('99%')
  })
})
