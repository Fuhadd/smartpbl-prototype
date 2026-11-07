/** Schedule panels, rebuilt from docs/design/screens/Schedule.dc.html. */
import { Check } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, XAxis, YAxis } from 'recharts'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { percent } from '@/overview/attention'

import type { Assignment, Run, RunMap, Tradeoff } from './api'
import {
  type CarerStats,
  colourOf,
  hhmm,
  IDLE_COLOUR,
  nextBestText,
  type NamedPreset,
  type Pins,
  PRESET_LABEL,
  PRESETS,
  timelineScale,
  windowText,
} from './model'

// --- Carers on shift ---------------------------------------------------------------------

export function CarersPanel({
  stats,
  pins,
  selected,
  onSelect,
  run,
  places,
}: {
  stats: CarerStats[]
  pins: Pins
  selected: string | null
  onSelect: (ref: string) => void
  run: Run
  places: RunMap | null
}) {
  const windows = new Map(places?.visits.map((v) => [v.visit_id, v]) ?? [])
  return (
    <section
      aria-labelledby="carers"
      className="flex max-w-[280px] min-w-0 flex-[1_1_240px] flex-col gap-1.5 rounded-[22px] bg-surface p-[18px] max-md:max-w-none"
    >
      <div className="flex items-center justify-between px-1.5 pb-1.5">
        <h2 id="carers" className="m-0 text-[15px] font-semibold">
          Carers on shift
        </h2>
        <span className="text-xs text-muted-foreground">{stats.length}</span>
      </div>
      <ul className="m-0 flex max-h-[520px] list-none flex-col gap-1.5 overflow-y-auto p-0">
        {stats.map((c) => (
          <li key={c.carerRef}>
            <button
              type="button"
              aria-pressed={selected === c.carerRef}
              onClick={() => onSelect(c.carerRef)}
              className={cn(
                'flex w-full cursor-pointer items-center gap-2.5 rounded-[14px] border-0 p-2.5 text-left',
                selected === c.carerRef ? 'bg-bg' : 'bg-transparent hover:bg-surface-muted',
              )}
            >
              <span
                className="size-3 flex-[0_0_12px] rounded-full"
                style={{ background: colourOf(pins, c.carerRef) ?? IDLE_COLOUR }}
                aria-hidden="true"
              />
              <span className="flex flex-1 flex-col">
                <span className="text-sm font-semibold">{c.carerRef}</span>
                <span className="text-xs text-muted-foreground">
                  {c.visits} visits · {c.travelMin} min travel
                </span>
              </span>
              <span className="text-xs font-semibold" title="Visits to a preferred or recent client">
                {percent(c.familiarPct)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <div className="mx-1.5 my-2 h-px bg-border" />
      <div className="flex items-center justify-between px-1.5 py-1">
        <span className="text-sm font-semibold">Unassigned</span>
        <span className="rounded-full bg-medium-bg px-2 py-0.5 text-xs font-semibold text-medium">{run.dropped.length}</span>
      </div>
      <ul className="m-0 flex max-h-[260px] list-none flex-col gap-1.5 overflow-y-auto p-0">
        {run.dropped.map((d) => {
          const v = windows.get(String(d.visit_id))
          return (
            <li key={String(d.visit_id)} className="flex flex-col gap-0.5 rounded-xl border border-dashed border-[#D4D4D8] px-2.5 py-2">
              <span className="text-[13px] font-semibold">
                {String(d.client_ref)}
                {v ? ` · ${windowText(v.window_start_min, v.window_end_min)}` : ''}
              </span>
              <span className="text-xs text-muted-foreground">{String(d.detail)}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// --- Timeline ----------------------------------------------------------------------------

export function TimelinePanel({
  run,
  pins,
  showAll,
  selectedVisit,
  onSelectVisit,
}: {
  run: Run
  pins: Pins
  showAll: boolean
  selectedVisit: string | null
  onSelectVisit: (visitId: string, carerRef: string) => void
}) {
  const routes = run.routes.filter((r) => r.visits.length && (showAll || pins.slots.includes(r.carer_ref)))
  if (!showAll) routes.sort((a, b) => pins.slots.indexOf(a.carer_ref) - pins.slots.indexOf(b.carer_ref))
  const { hours, place } = timelineScale(routes)
  return (
    <section aria-labelledby="tl" className="flex flex-col gap-3 rounded-[22px] bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 id="tl" className="m-0 text-[15px] font-semibold">
          Timeline
        </h2>
        <span className="text-xs text-muted-foreground">Visits as blocks · gaps are travel</span>
      </div>
      <div className="overflow-x-auto">
        <div className="flex min-w-[560px] flex-col gap-2.5">
          <div className="grid grid-cols-[96px_1fr] text-[11px] text-muted-foreground" aria-hidden="true">
            <span />
            <div className="grid" style={{ gridTemplateColumns: `repeat(${hours.length}, minmax(0, 1fr))` }}>
              {hours.map((h) => (
                <span key={h}>{`${String(h).padStart(2, '0')}:00`}</span>
              ))}
            </div>
          </div>
          {routes.map((r) => {
            const colour = colourOf(pins, r.carer_ref) ?? '#71717A'
            return (
              <div key={r.carer_ref} className="grid grid-cols-[96px_1fr] items-center">
                <span className="text-[13px] font-semibold">{r.carer_ref}</span>
                <div className="relative h-8 rounded-lg bg-surface-muted">
                  {r.visits.map((v) => {
                    const { left, width } = place(v)
                    const selected = v.visit_id === selectedVisit
                    return (
                      <button
                        key={v.visit_id}
                        type="button"
                        aria-pressed={selected}
                        aria-label={`${r.carer_ref} visit ${v.sequence}: ${v.client_ref}, ${hhmm(v.start_s)} to ${hhmm(v.end_s)}`}
                        title={`${v.client_ref} · ${hhmm(v.start_s)}–${hhmm(v.end_s)}`}
                        onClick={() => onSelectVisit(v.visit_id, r.carer_ref)}
                        className={cn(
                          'absolute cursor-pointer rounded-[6px] border-0 p-0',
                          selected ? 'top-0 bottom-0 outline-2 outline-offset-2 outline-primary' : 'top-1 bottom-1',
                        )}
                        style={{ left: `${left}%`, width: `${width}%`, background: colour }}
                      />
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// --- Visit: why this carer ---------------------------------------------------------------

export function VisitPanel({
  visit,
  colour,
  places,
}: {
  visit: Assignment | null
  colour: string
  places: RunMap | null
}) {
  if (!visit)
    return (
      <section className="rounded-[22px] bg-surface p-5 text-sm text-muted-foreground">
        Choose a visit on the map or timeline to see why its carer was assigned.
      </section>
    )
  const place = places?.visits.find((v) => v.visit_id === visit.visit_id)
  const next = nextBestText(visit)
  return (
    <section aria-labelledby="visit" className="flex flex-col gap-3.5 rounded-[22px] bg-surface p-5">
      <div className="flex items-center gap-2.5">
        <span
          className="flex size-9 items-center justify-center rounded-full text-sm font-bold text-white"
          style={{ background: colour }}
          aria-hidden="true"
        >
          {visit.sequence}
        </span>
        <div className="flex flex-col">
          <h2 id="visit" className="m-0 text-base font-semibold">
            {visit.client_ref} · {visit.carer_ref}
          </h2>
          <span className="text-[13px] text-muted-foreground">
            {place ? `Window ${windowText(place.window_start_min, place.window_end_min)} · ` : ''}arrives {hhmm(visit.start_s)}
          </span>
        </div>
      </div>
      <h3 className="m-0 text-xs font-semibold tracking-[0.06em] text-muted-foreground">
        WHY {visit.carer_ref} WAS ASSIGNED
      </h3>
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0 text-sm">
        {visit.reasons.map((r) => (
          <li key={r} className="flex items-start gap-2.5">
            <Check size={16} strokeWidth={2.25} className="mt-0.5 flex-none text-success" aria-hidden="true" />
            <span>{r}</span>
          </li>
        ))}
      </ul>
      {next ? (
        <div className="rounded-[14px] bg-surface-muted px-3.5 py-3 text-[13px] leading-normal text-soft">
          Next best: <strong className="text-text">{next.carer}</strong> · {next.rest}
          <span className="mt-1 block text-xs text-muted-foreground">Closest other qualified carer, before any re-planning.</span>
        </div>
      ) : (
        <div className="rounded-[14px] bg-surface-muted px-3.5 py-3 text-[13px] text-soft">
          No other qualified carer was on shift for this visit.
        </div>
      )}
    </section>
  )
}

// --- Optimise for (trade-off) ------------------------------------------------------------

export function TradeoffPanel({
  tradeoff,
  choice,
  onChoose,
  onApply,
  applying,
  canSolve,
  current,
}: {
  tradeoff: Tradeoff
  choice: NamedPreset
  onChoose: (p: NamedPreset) => void
  onApply: () => void
  applying: boolean
  canSolve: boolean
  current: NamedPreset | 'custom'
}) {
  const front = tradeoff.points
    .filter((p) => p.pareto)
    .map((p) => ({ x: Math.round(p.familiar_pct * 100), y: Math.round((p.drive_min / 60) * 10) / 10, w: p.weight_min }))
    .sort((a, b) => a.x - b.x)
  const at = (w: number) => tradeoff.points.find((p) => p.weight_min === w)!
  const chosen = at(tradeoff.presets[choice]!)
  const fastest = at(tradeoff.presets.travel!)
  const point = { x: Math.round(chosen.familiar_pct * 100), y: Math.round((chosen.drive_min / 60) * 10) / 10 }
  const extraH = (chosen.drive_min - fastest.drive_min) / 60
  const gain = Math.round((chosen.familiar_pct - fastest.familiar_pct) * 100)
  const lo = front[0]!
  const hi = front[front.length - 1]!
  const label = `Trade-off curve: as continuity rises from ${lo.x} to ${hi.x} percent, total travel rises from ${lo.y} to ${hi.y} hours; the ${PRESET_LABEL[choice].toLowerCase()} setting sits at ${point.x} percent and ${point.y} hours`

  return (
    <section aria-labelledby="trade" className="flex flex-col gap-3.5 rounded-[22px] bg-surface p-5">
      <h2 id="trade" className="m-0 text-[15px] font-semibold">
        Optimise for
      </h2>
      <div role="group" aria-label="Optimisation priority" className="grid grid-cols-3 gap-1 rounded-xl bg-bg p-1">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={choice === p}
            onClick={() => onChoose(p)}
            className={cn(
              'h-9 cursor-pointer rounded-[9px] border-0 text-[13px]',
              choice === p ? 'bg-surface font-semibold text-text shadow-[0_1px_2px_rgba(0,0,0,0.08)]' : 'bg-transparent font-medium text-soft',
            )}
          >
            {PRESET_LABEL[p]}
          </button>
        ))}
      </div>
      <figure className="m-0" role="img" aria-label={label}>
        <ResponsiveContainer width="100%" height={150} initialDimension={{ width: 280, height: 150 }}>
          <LineChart data={front} margin={{ top: 12, right: 12, bottom: 16, left: 0 }}>
            <CartesianGrid stroke="#E7E7E4" vertical={false} />
            <XAxis
              dataKey="x"
              type="number"
              domain={['dataMin - 2', 'dataMax + 2']}
              tick={{ fontSize: 10, fill: '#5F5F66' }}
              tickFormatter={(v: number) => `${v}%`}
              label={{ value: 'Continuity of care →', position: 'insideBottom', offset: -10, fontSize: 10, fill: '#5F5F66' }}
            />
            <YAxis
              dataKey="y"
              width={36}
              domain={['dataMin - 0.5', 'dataMax + 0.5']}
              tick={{ fontSize: 10, fill: '#5F5F66' }}
              tickFormatter={(v: number) => v.toFixed(0)}
              label={{ value: 'Travel (h) →', angle: -90, position: 'insideLeft', offset: 10, fontSize: 10, fill: '#5F5F66' }}
            />
            <Line type="monotone" dataKey="y" stroke="#A1A1AA" strokeWidth={2} dot={{ r: 3, fill: '#A1A1AA' }} isAnimationActive={false} />
            <ReferenceDot x={point.x} y={point.y} r={6} fill="#111113" stroke="rgba(17,17,19,0.12)" strokeWidth={8}
              label={{ value: `${point.x}% · ${point.y} h`, position: 'right', fontSize: 10, fontWeight: 600, fill: '#18181B' }} />
          </LineChart>
        </ResponsiveContainer>
        <figcaption className="text-[11px] text-muted-foreground">
          Sample-day sweep, {tradeoff.visits} visits, {tradeoff.time_limit_s} s per point
        </figcaption>
      </figure>
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-0.5 rounded-xl bg-surface-muted p-3">
          <span className="text-xs text-muted-foreground">Travel vs fastest</span>
          <span className="text-lg font-bold">{`${extraH >= 0 ? '+' : '−'}${Math.abs(extraH).toFixed(1)} h`}</span>
        </div>
        <div className="flex flex-col gap-0.5 rounded-xl bg-surface-muted p-3">
          <span className="text-xs text-muted-foreground">Continuity gain</span>
          <span className="text-lg font-bold">{`${gain >= 0 ? '+' : '−'}${Math.abs(gain)} pts`}</span>
        </div>
      </div>
      {canSolve ? (
        <Button type="button" onClick={onApply} disabled={applying} className="h-11 cursor-pointer rounded-xl text-sm font-semibold">
          {applying ? 'Re-optimising…' : 'Apply and re-optimise'}
        </Button>
      ) : (
        <p className="m-0 text-[13px] text-muted-foreground">Coordinators re-optimise the rota; care managers can review it.</p>
      )}
      {current !== choice && (
        <p className="m-0 text-xs text-muted-foreground">
          The saved rota uses {PRESET_LABEL[current]}. Nothing changes until you apply.
        </p>
      )}
    </section>
  )
}
