/**
 * Reusable page states, rebuilt from docs/design/screens/States.dc.html:
 * empty (review queue), loading (overview), error (schedule), access denied (wrong role).
 * Copy defaults are the design's exact wording; screens pass their own where it differs.
 */
import { Check, Lock, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function StateCard({ children, role }: { children: ReactNode; role?: 'alert' }) {
  return (
    <Card
      role={role}
      className="flex-1 items-center justify-center gap-3 rounded-3xl border-0 p-8 text-center shadow-none"
    >
      {children}
    </Card>
  )
}

function StateIcon({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span className={cn('flex size-16 items-center justify-center rounded-full', className)} aria-hidden="true">
      {children}
    </span>
  )
}

function Title({ children }: { children: ReactNode }) {
  return <h3 className="m-0 text-xl font-bold">{children}</h3>
}

function Body({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <p className={cn('m-0 text-sm leading-normal text-muted-foreground', wide ? 'max-w-[380px]' : 'max-w-[360px]')}>
      {children}
    </p>
  )
}

export type Action = { label: string; to: string; external?: boolean }

function ActionLink({ action, primary }: { action: Action; primary?: boolean }) {
  return (
    <Button asChild size="pill" variant={primary ? 'default' : 'outline'} className="mt-1">
      {action.external ? <a href={action.to}>{action.label}</a> : <Link to={action.to}>{action.label}</Link>}
    </Button>
  )
}

export function EmptyState({
  title = 'All caught up',
  message = 'No care notes are waiting for review. New flags appear here automatically.',
  action = { label: 'View recent decisions', to: '/audit' },
}: {
  title?: string
  message?: string
  action?: Action
}) {
  return (
    <StateCard>
      <StateIcon className="bg-success-bg text-success">
        <Check size={30} strokeWidth={2.25} />
      </StateIcon>
      <Title>{title}</Title>
      <Body>{message}</Body>
      <ActionLink action={action} />
    </StateCard>
  )
}

export function LoadingOverview({ label = 'Loading overview' }: { label?: string }) {
  const rows = [
    ['w-[60%]', 'w-[40%]'],
    ['w-[52%]', 'w-[34%]'],
    ['w-[66%]', 'w-[30%]'],
  ]
  return (
    <Card aria-busy="true" className="flex-1 gap-[18px] rounded-3xl border-0 p-7 shadow-none">
      <span className="sr-only">{label}</span>
      <Skeleton className="h-[22px] w-[220px] rounded-lg bg-skeleton-strong" />
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-[92px] rounded-2xl" />
        ))}
      </div>
      {rows.map(([a, b]) => (
        <div key={a} className="flex items-center gap-3.5">
          <Skeleton className="size-11 rounded-[14px]" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className={cn('h-3 rounded-[6px] bg-skeleton-strong', a)} />
            <Skeleton className={cn('h-2.5 rounded-[6px]', b)} />
          </div>
        </div>
      ))}
    </Card>
  )
}

export function ErrorState({
  title = "Couldn't re-optimise the schedule",
  message = "The optimiser didn't respond in time. Your last saved rota is still in place, so nothing has changed for carers.",
  onRetry,
  secondary = { label: 'View saved rota', to: '/schedule' },
  onSecondary,
  reference,
}: {
  title?: string
  message?: string
  onRetry?: () => void
  secondary?: Action
  /** Makes the secondary action a button (e.g. dismiss the error and show the saved rota). */
  onSecondary?: () => void
  /** Server request reference ("req_8f2c41"), from the X-Request-ID response header. */
  reference?: string | null
}) {
  return (
    <StateCard role="alert">
      <StateIcon className="bg-medium-bg text-medium">
        <TriangleAlert size={30} strokeWidth={2} />
      </StateIcon>
      <Title>{title}</Title>
      <Body wide>{message}</Body>
      <div className="mt-1 flex gap-2.5">
        {onRetry && (
          <Button type="button" size="pill" onClick={onRetry} className="cursor-pointer">
            Try again
          </Button>
        )}
        {onSecondary ? (
          <Button type="button" size="pill" variant="outline" onClick={onSecondary} className="mt-1 cursor-pointer">
            {secondary.label}
          </Button>
        ) : (
          <ActionLink action={secondary} />
        )}
      </div>
      {reference && <span className="font-mono text-xs text-muted-foreground">Reference: {reference}</span>}
    </StateCard>
  )
}

export function AccessDenied({
  subject,
  signedInAs,
  back,
  recorded,
}: {
  /** e.g. "Workforce risk is visible to coordinators and care managers." */
  subject: string
  /** e.g. "Joy A. (carer)" */
  signedInAs: string
  back: Action
  /** Shown only once the server has actually refused (and so logged) the attempt. */
  recorded: boolean
}) {
  return (
    <StateCard>
      <StateIcon className="bg-bg text-text">
        <Lock size={28} strokeWidth={1.75} />
      </StateIcon>
      <Title>You don't have access to this page</Title>
      <Body wide>
        {subject} You're signed in as <strong className="text-text">{signedInAs}</strong>.
      </Body>
      <ActionLink action={back} primary />
      {recorded && <span className="text-xs text-muted-foreground">This attempt was recorded in the audit log.</span>}
    </StateCard>
  )
}
