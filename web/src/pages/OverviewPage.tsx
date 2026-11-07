/** Overview: docs/design/screens/Main.dc.html. One /overview request feeds every panel. */
import { useState } from 'react'

import { ApiError } from '@/api/client'
import { PageContainer, PageHeader } from '@/app/AppShell'
import { firstName, useAuth } from '@/auth/auth'
import { ErrorState, LoadingOverview } from '@/components/states/States'
import { TEAM_NAME } from '@/config'
import { greeting, longDate } from '@/lib/dates'
import { useOverview } from '@/overview/api'
import { AtAGlance, FlagsByCategory, NeedsAttention, PipelineHealth, TodaysSchedule } from '@/overview/panels'

export function OverviewPage() {
  const { me } = useAuth()
  const [now] = useState(() => new Date()) // once per visit: the greeting doesn't flicker
  const overview = useOverview()
  if (!me) return null
  return (
    <PageContainer>
      <PageHeader title="Overview" />
      <section className="flex flex-col gap-1">
        <h1 className="m-0 text-[34px] leading-[1.15] font-bold tracking-[-0.02em]">
          {greeting(now)}, {firstName(me)}
        </h1>
        <p className="m-0 text-[15px] text-muted-foreground">
          {longDate(now)} · {TEAM_NAME}
        </p>
      </section>
      {overview.isPending ? (
        <div className="flex min-h-[420px]">
          <LoadingOverview />
        </div>
      ) : overview.isError ? (
        <div className="flex min-h-[420px]">
          <ErrorState
            title="Couldn't load the overview"
            message="The summary didn't load. Nothing has changed: flags, rotas and decisions are all still saved."
            onRetry={() => overview.refetch()}
            secondary={{ label: 'Open review queue', to: '/review' }}
            reference={overview.error instanceof ApiError ? overview.error.reference : null}
          />
        </div>
      ) : (
        <>
          <AtAGlance data={overview.data} />
          <div className="flex flex-wrap items-start gap-6">
            <NeedsAttention data={overview.data} />
            <div className="flex min-w-0 flex-[1_1_340px] flex-col gap-6">
              <FlagsByCategory data={overview.data} />
              <TodaysSchedule data={overview.data} />
              <PipelineHealth data={overview.data} />
            </div>
          </div>
        </>
      )}
    </PageContainer>
  )
}
