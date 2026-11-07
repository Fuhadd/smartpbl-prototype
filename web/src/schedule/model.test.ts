import { describe, expect, it } from 'vitest'

import { runFixture } from '@/test/scheduleFixtures'

import type { Run } from './api'
import { carerStats, colourOf, hhmm, initialPins, nextBestText, pin, runPreset, timelineScale, windowText } from './model'

const run = runFixture() as unknown as Run

describe('carer stats', () => {
  it('counts visits, travel and the share of familiar visits', () => {
    expect(carerStats(run)[0]).toEqual({ carerRef: 'CR-0001', visits: 2, travelMin: 38, familiarPct: 0.5 })
  })
})

describe('pinned routes', () => {
  it('colours the first three carers and keeps a colour while pinned', () => {
    const p = initialPins(['CR-0001', 'CR-0002', 'CR-0003', 'CR-0004'])
    expect(p.slots).toEqual(['CR-0001', 'CR-0002', 'CR-0003'])
    expect(colourOf(p, 'CR-0004')).toBeNull()
    const again = pin(p, 'CR-0002')
    expect(colourOf(again, 'CR-0002')).toBe(colourOf(p, 'CR-0002'))
  })

  it('replaces the least recently chosen carer, in its slot', () => {
    let p = initialPins(['CR-0001', 'CR-0002', 'CR-0003'])
    p = pin(p, 'CR-0003') // recency is now 3, 1, 2: CR-0002 is the oldest pick
    p = pin(p, 'CR-0009')
    expect(p.slots).toEqual(['CR-0001', 'CR-0009', 'CR-0003'])
  })
})

describe('timeline', () => {
  it('spans whole hours around the visits and places blocks by time', () => {
    const { hours, place } = timelineScale(run.routes)
    expect(hours).toEqual([7, 8, 9, 10, 11])
    const first = run.routes[0]!.visits[0]!
    expect(place(first)).toEqual({ left: 0, width: 10 })
  })
})

describe('copy', () => {
  it('formats times, windows and the next-best carer', () => {
    expect(hhmm(9 * 3600 + 40 * 60)).toBe('09:40')
    expect(windowText(570, 615)).toBe('09:30–10:15')
    expect(nextBestText(run.routes[0]!.visits[0]!)).toEqual({ carer: 'CR-0003', rest: '+22 min travel, new to this client' })
    expect(nextBestText(run.routes[2]!.visits[0]!)).toBeNull()
  })

  it('names the run preset from its continuity weight', () => {
    expect(runPreset(run, { travel: 0, balanced: 15, continuity: 30 })).toBe('balanced')
    const odd = runFixture({ params: { continuity_weight_min: 20 } }) as unknown as Run
    expect(runPreset(odd, { travel: 0, balanced: 15, continuity: 30 })).toBe('custom')
  })
})
