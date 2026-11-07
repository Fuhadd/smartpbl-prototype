/** Schedule & map: docs/design/screens/Schedule.dc.html. */
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'

import { DemoBadge } from '@/app/AppShell'
import { useAuth } from '@/auth/auth'
import { ErrorState, LoadingOverview } from '@/components/states/States'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { type Run, type RunMap, useLatestSchedule, useRunMap, useSolve, useTradeoff } from '@/schedule/api'
import {
  carerStats,
  colourOf,
  initialPins,
  type NamedPreset,
  pin,
  type Pins,
  runPreset,
  SOLVE_HINT,
} from '@/schedule/model'
import { CarersPanel, TimelinePanel, TradeoffPanel, VisitPanel } from '@/schedule/panels'
import { RouteMap } from '@/schedule/RouteMap'

type View = 'map' | 'timeline'

function runDate(run: Run | null | undefined): string {
  const d = run ? new Date(run.created_at) : new Date()
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '')
}

export function SchedulePage() {
  const { can } = useAuth()
  const canSolve = can('schedule.solve')
  const latest = useLatestSchedule()
  const run = latest.data ?? null
  const places = useRunMap(run?.id)
  const tradeoff = useTradeoff()
  const solve = useSolve()

  const [view, setView] = useState<View>('map')
  const [choice, setChoice] = useState<NamedPreset | null>(null)
  const [showError, setShowError] = useState(false)

  const current = run && tradeoff.data ? runPreset(run, tradeoff.data.presets) : 'custom'
  const chosen: NamedPreset = choice ?? (current === 'custom' ? 'balanced' : current)

  function reoptimise(preset: NamedPreset) {
    if (!tradeoff.data) return
    setShowError(false)
    solve.mutate(tradeoff.data.presets[preset]!, {
      onSuccess: () => setChoice(null),
      onError: () => setShowError(true),
    })
  }

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3.5">
        <h1 className="m-0 text-[28px] font-bold tracking-[-0.02em]">Schedule</h1>
        {/* One synthetic day in the prototype: the day switcher shows it but can't move. */}
        <div className="flex items-center gap-1 rounded-full border border-border bg-surface p-1" title="The prototype plans one synthetic day">
          <button type="button" aria-label="Previous day" disabled className="flex size-8 items-center justify-center rounded-full border-0 bg-transparent text-text disabled:opacity-40">
            <ChevronLeft size={16} strokeWidth={1.75} aria-hidden="true" />
          </button>
          <span className="px-1.5 text-sm font-semibold">{runDate(run)}</span>
          <button type="button" aria-label="Next day" disabled className="flex size-8 items-center justify-center rounded-full border-0 bg-transparent text-text disabled:opacity-40">
            <ChevronRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
        <DemoBadge />
      </div>
      <div className="flex items-center gap-2.5">
        <div className="flex rounded-full border border-border bg-surface p-1">
          {(['map', 'timeline'] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={cn(
                'h-9 cursor-pointer rounded-full border-0 px-[18px] text-sm font-medium',
                view === v ? 'bg-primary text-primary-foreground' : 'bg-transparent text-text',
              )}
            >
              {v === 'map' ? 'Map' : 'Timeline'}
            </button>
          ))}
        </div>
        {canSolve && (
          <Button
            type="button"
            size="pill"
            className="h-11 cursor-pointer"
            disabled={solve.isPending || !tradeoff.data}
            onClick={() => reoptimise(current === 'custom' ? 'balanced' : current)}
          >
            {solve.isPending ? 'Re-optimising…' : 'Re-optimise'}
          </Button>
        )}
      </div>
    </header>
  )

  let body
  if (latest.isPending) {
    body = (
      <div className="flex min-h-[420px]">
        <LoadingOverview label="Loading schedule" />
      </div>
    )
  } else if (latest.isError) {
    body = (
      <div className="flex min-h-[420px]">
        <ErrorState
          title="Couldn't load the schedule"
          message="The saved rota didn't load. Nothing has changed for carers."
          onRetry={() => latest.refetch()}
          secondary={{ label: 'Back to overview', to: '/' }}
          reference={latest.error && 'reference' in latest.error ? (latest.error.reference as string | null) : null}
        />
      </div>
    )
  } else if (showError && solve.error) {
    body = (
      <div className="flex min-h-[420px]">
        {/* The States sheet's error exactly: a failed solve leaves the saved rota in place. */}
        <ErrorState
          title={solve.error.status === 429 ? 'Re-optimised too recently' : undefined}
          message={
            solve.error.status === 429
              ? `Each coordinator can re-optimise a few times a minute. Try again in ${solve.error.retryAfterS ?? 60} s. Your last saved rota is still in place.`
              : undefined
          }
          onRetry={() => reoptimise(chosen)}
          onSecondary={() => setShowError(false)}
          reference={solve.error.reference}
        />
      </div>
    )
  } else if (!run) {
    body = (
      <section className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-3xl bg-surface p-8 text-center">
        <h2 className="m-0 text-xl font-bold">No rota saved yet</h2>
        <p className="m-0 max-w-[380px] text-sm text-muted-foreground">
          {canSolve
            ? 'Run the optimiser to plan the sample day. It takes up to 20 seconds.'
            : 'A coordinator needs to run the optimiser first.'}
        </p>
        {canSolve && (
          <Button type="button" size="pill" className="cursor-pointer" disabled={solve.isPending || !tradeoff.data}
            onClick={() => reoptimise('balanced')}>
            {solve.isPending ? 'Optimising…' : 'Optimise the day'}
          </Button>
        )}
      </section>
    )
  } else {
    // Keyed by run: a new run (after re-optimising) starts with fresh pins and selection.
    body = (
      <RunView
        key={run.id}
        run={run}
        places={places.data ?? null}
        placesPending={places.isPending}
        view={view}
        trade={
          tradeoff.data && (
            <TradeoffPanel
              tradeoff={tradeoff.data}
              choice={chosen}
              onChoose={setChoice}
              onApply={() => reoptimise(chosen)}
              applying={solve.isPending}
              canSolve={canSolve}
              current={current}
            />
          )
        }
      />
    )
  }

  return (
    <main className="flex flex-col gap-5 px-8 pt-6 pb-10 max-sm:px-4">
      {header}
      {solve.isPending && (
        <p role="status" className="m-0 rounded-2xl bg-ai-bg px-4 py-3 text-sm text-ai-text">
          {SOLVE_HINT}
        </p>
      )}
      {body}
    </main>
  )
}

function RunView({
  run,
  places,
  placesPending,
  view,
  trade,
}: {
  run: Run
  places: RunMap | null
  placesPending: boolean
  view: View
  trade: ReactNode
}) {
  const stats = useMemo(() => carerStats(run), [run])
  const [pins, setPins] = useState<Pins>(() => initialPins(stats.map((c) => c.carerRef)))
  const [selectedCarer, setSelectedCarer] = useState<string | null>(stats[0]?.carerRef ?? null)
  const [selectedVisit, setSelectedVisit] = useState<string | null>(
    () => run.routes.find((r) => r.carer_ref === stats[0]?.carerRef)?.visits[0]?.visit_id ?? null,
  )
  const assignment = run.routes.flatMap((r) => r.visits).find((v) => v.visit_id === selectedVisit) ?? null

  function selectCarer(ref: string) {
    setPins((p) => pin(p, ref))
    setSelectedCarer(ref)
    setSelectedVisit(run.routes.find((r) => r.carer_ref === ref)?.visits[0]?.visit_id ?? null)
  }

  function selectVisit(visitId: string, carerRef?: string) {
    const ref = carerRef ?? run.routes.find((r) => r.visits.some((v) => v.visit_id === visitId))?.carer_ref
    if (ref) {
      setPins((p) => pin(p, ref))
      setSelectedCarer(ref)
    }
    setSelectedVisit(visitId)
  }

  const selColour = (selectedCarer && colourOf(pins, selectedCarer)) || '#71717A'
  return (
    <div className="flex flex-wrap items-start gap-5">
      <CarersPanel stats={stats} pins={pins} selected={selectedCarer} onSelect={selectCarer} run={run} places={places} />
      <div className="flex min-w-0 flex-[999_1_480px] flex-col gap-5">
        {view === 'map' && (
          <section aria-label="Route map" className="rounded-[22px] bg-surface p-2.5">
            {placesPending ? (
              <div className="h-[440px] rounded-2xl bg-skeleton motion-safe:animate-pulse" aria-busy="true" />
            ) : places ? (
              <RouteMap run={run} places={places} pins={pins} selectedVisit={selectedVisit} onSelectVisit={selectVisit} />
            ) : (
              <p className="m-0 flex h-[200px] items-center justify-center p-6 text-center text-sm text-muted-foreground">
                Runs don't store where clients live, so the map is only available for the sample day.
              </p>
            )}
          </section>
        )}
        <TimelinePanel run={run} pins={pins} showAll={view === 'timeline'} selectedVisit={selectedVisit} onSelectVisit={selectVisit} />
      </div>
      <aside aria-label="Visit and trade-off" className="flex max-w-[340px] min-w-0 flex-[1_1_300px] flex-col gap-4 max-md:max-w-none">
        <VisitPanel visit={assignment} colour={selColour} places={places} />
        {trade}
      </aside>
    </div>
  )
}
