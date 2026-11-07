/** Carer risk detail: docs/design/screens/Workforce.dc.html. The list is its left panel. */
import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router'

import { ApiError } from '@/api/client'
import { DemoBadge } from '@/app/AppShell'
import { useAuth } from '@/auth/auth'
import { EmptyState, ErrorState, LoadingOverview } from '@/components/states/States'
import { Skeleton } from '@/components/ui/skeleton'
import { type Explanation, useExplanation, useRiskList } from '@/workforce/api'
import { supportActions } from '@/workforce/model'
import {
  ActionsPanel,
  CarerHeader,
  DriversPanel,
  KeySignals,
  ModelCardPanel,
  RiskListPanel,
  UseNotice,
} from '@/workforce/panels'

const reference = (e: unknown) => (e instanceof ApiError ? e.reference : null)

export function WorkforcePage() {
  const { carerId } = useParams()
  const list = useRiskList()
  const detail = useExplanation(carerId)
  const [showCard, setShowCard] = useState(false)

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2.5 text-sm">
        <Link to="/workforce" className="text-muted-foreground">
          Workforce
        </Link>
        {carerId && (
          <>
            <span className="text-faint" aria-hidden="true">
              /
            </span>
            <span className="font-semibold">{carerId}</span>
          </>
        )}
        <DemoBadge />
      </div>
      <button
        type="button"
        aria-expanded={showCard}
        aria-controls="model-card"
        disabled={!detail.data}
        onClick={() => setShowCard((s) => !s)}
        className="flex h-10 cursor-pointer items-center rounded-full border border-border bg-surface px-4 text-sm font-medium disabled:cursor-default disabled:opacity-60"
      >
        Model card
      </button>
    </header>
  )

  let body
  if (list.isPending) {
    body = <LoadingOverview label="Loading workforce" />
  } else if (list.isError) {
    body = (
      <ErrorState
        title="Couldn't load workforce risk"
        message="The risk estimates didn't load. Nothing has been changed for any carer."
        onRetry={() => void list.refetch()}
        secondary={{ label: 'Back to overview', to: '/' }}
        reference={reference(list.error)}
      />
    )
  } else if (!carerId) {
    // Open on the carer the model ranks highest, as the review screen opens on the first note.
    const first = list.data.carers[0]
    if (first) return <Navigate to={`/workforce/${first.carer_ref}`} replace />
    body = (
      <EmptyState
        title="No carers scored yet"
        message="Risk estimates appear here once the model has scored the current workforce."
        action={{ label: 'Back to overview', to: '/' }}
      />
    )
  }
  if (body)
    return (
      <main className="flex flex-col gap-5 px-8 pt-6 pb-10 max-sm:px-4">
        {header}
        <div className="flex min-h-[420px]">{body}</div>
      </main>
    )

  return (
    <main className="flex flex-col gap-5 px-8 pt-6 pb-10 max-sm:px-4">
      {header}
      <div className="flex flex-wrap items-start gap-5">
        <RiskListPanel carers={list.data!.carers} total={list.data!.total} selected={carerId} />
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          {detail.isPending ? (
            <div className="flex flex-col gap-5" aria-busy="true" aria-label="Loading carer">
              <Skeleton className="h-28 rounded-3xl" />
              <Skeleton className="h-24 rounded-[20px]" />
              <Skeleton className="h-80 rounded-3xl" />
            </div>
          ) : detail.isError ? (
            <ErrorState
              title="Couldn't load this explanation"
              message="The estimate for this carer didn't load. Nothing has been changed."
              onRetry={() => void detail.refetch()}
              secondary={{ label: 'Back to workforce', to: '/workforce' }}
              reference={reference(detail.error)}
            />
          ) : detail.data ? (
            <Detail e={detail.data} showCard={showCard} />
          ) : (
            <section className="flex min-h-[240px] flex-col items-center justify-center gap-2 rounded-3xl bg-surface p-8 text-center">
              <h1 className="m-0 text-xl font-bold">Carer not found</h1>
              <p className="m-0 text-sm text-muted-foreground">{carerId} isn't in the current workforce.</p>
            </section>
          )}
        </div>
      </div>
    </main>
  )
}

function Detail({ e, showCard }: { e: Explanation; showCard: boolean }) {
  const { can } = useAuth()
  return (
    <>
      {showCard && <ModelCardPanel e={e} />}
      <CarerHeader e={e} />
      <KeySignals e={e} />
      <DriversPanel e={e} />
      <ActionsPanel actions={supportActions(e)} canSchedule={can('schedule.read')} />
      <UseNotice />
    </>
  )
}
