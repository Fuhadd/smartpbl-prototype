/** The schedule screen, loaded on first visit: Leaflet and Recharts are about half the
 * bundle, and only this screen uses them. */
import { lazy, Suspense } from 'react'

import { LoadingOverview } from '@/components/states/States'

const SchedulePage = lazy(() => import('./SchedulePage').then((m) => ({ default: m.SchedulePage })))

export function LazySchedulePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[420px] p-8">
          <LoadingOverview label="Loading schedule" />
        </div>
      }
    >
      <SchedulePage />
    </Suspense>
  )
}
