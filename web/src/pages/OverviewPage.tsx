/** Overview: docs/design/screens/Main.dc.html. Step 5.1 builds the frame (header,
 * greeting); the at-a-glance tiles and panels need a summary endpoint and land in 5.2. */
import { useState } from 'react'

import { PageHeader } from '@/app/AppShell'
import { firstName, useAuth } from '@/auth/auth'
import { TEAM_NAME } from '@/config'

import { greeting, longDate } from '@/lib/dates'

import { PendingStep } from './PendingStep'

export function OverviewPage() {
  const { me } = useAuth()
  const [now] = useState(() => new Date()) // once per visit: the greeting doesn't flicker
  if (!me) return null
  return (
    <>
      <PageHeader title="Overview" />
      <section className="flex flex-col gap-1">
        <h1 className="m-0 text-[34px] leading-[1.15] font-bold tracking-[-0.02em]">
          {greeting(now)}, {firstName(me)}
        </h1>
        <p className="m-0 text-[15px] text-muted-foreground">
          {longDate(now)} · {TEAM_NAME}
        </p>
      </section>
      <PendingStep step="5.2" what="Today at a glance, needs attention and pipeline health" />
    </>
  )
}
