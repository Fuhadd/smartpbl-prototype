import { PageContainer, PageHeader } from '@/app/AppShell'
import { page, type PageKey } from '@/app/pages'

import { PendingStep } from './PendingStep'

/** A rail destination whose screen a later Tier 5 step builds. */
export function PendingPage({ pageKey, step }: { pageKey: PageKey; step: string }) {
  const def = page(pageKey)
  return (
    <PageContainer>
      <PageHeader title={def.title} />
      <PendingStep step={step} what={`The ${def.title.toLowerCase()} screen and its data`} />
    </PageContainer>
  )
}
