/** Screens loaded on first visit, keeping the sign-in and overview bundle under 500 kB.
 * Schedule: Leaflet and Recharts are about half the app and only that screen uses them.
 * Workforce: small, but read by few roles and rarely, so it needn't ship to everyone. */
import { lazy, Suspense } from 'react'

import { LoadingOverview } from '@/components/states/States'

const SchedulePage = lazy(() => import('./SchedulePage').then((m) => ({ default: m.SchedulePage })))
const WorkforcePage = lazy(() => import('./WorkforcePage').then((m) => ({ default: m.WorkforcePage })))

function Loading({ label }: { label: string }) {
  return (
    <div className="flex min-h-[420px] p-8">
      <LoadingOverview label={label} />
    </div>
  )
}

export function LazySchedulePage() {
  return (
    <Suspense fallback={<Loading label="Loading schedule" />}>
      <SchedulePage />
    </Suspense>
  )
}

export function LazyWorkforcePage() {
  return (
    <Suspense fallback={<Loading label="Loading workforce" />}>
      <WorkforcePage />
    </Suspense>
  )
}
