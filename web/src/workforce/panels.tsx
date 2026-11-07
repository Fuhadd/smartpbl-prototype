/** Workforce.dc.html panels: risk list, carer header, key signals, SHAP drivers, actions. */
import {
  CalendarDays,
  FileText,
  GraduationCap,
  Info,
  MapPin,
  MessageSquare,
  UserRound,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { Band, Explanation, RiskItem } from './api'
import {
  BAND_BADGE,
  BAND_LABEL,
  barWidth,
  driverRows,
  factorOf,
  KEY_SIGNALS,
  percent,
  profileLine,
  signedPoints,
  type ActionKind,
  type SupportAction,
} from './model'

const TILE: Record<Band, string> = {
  elevated: 'bg-elevated-bg text-elevated-strong',
  moderate: 'bg-medium-bg text-medium',
  low: 'bg-success-bg text-success',
}

function Avatar({ selected, large = false }: { selected: boolean; large?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full',
        large ? 'size-16' : 'size-[34px]',
        selected ? 'bg-avatar text-ai-text' : 'bg-bg text-soft',
      )}
    >
      <UserRound size={large ? 28 : 16} strokeWidth={1.75} />
    </span>
  )
}

export function RiskListPanel({ carers, total, selected }: { carers: RiskItem[]; total: number; selected: string | undefined }) {
  return (
    <section
      aria-labelledby="risklist"
      className="flex max-w-[280px] min-w-0 flex-[1_1_240px] flex-col gap-1 rounded-[22px] bg-surface p-[18px] max-md:max-w-none"
    >
      <div className="flex items-center justify-between px-1.5 pb-2">
        <h2 id="risklist" className="m-0 text-[15px] font-semibold">
          Carers by risk
        </h2>
        <span className="text-xs text-muted-foreground">{total}</span>
      </div>
      {/* The whole workforce in one scrolling list, highest risk first. */}
      <nav aria-label="Carers by risk" className="-mx-1 flex max-h-[640px] flex-col gap-1 overflow-y-auto px-1">
        {carers.map((c) => {
          const current = c.carer_ref === selected
          return (
            <Link
              key={c.carer_ref}
              to={`/workforce/${c.carer_ref}`}
              aria-current={current ? 'page' : undefined}
              className={cn('flex items-center gap-2.5 rounded-[14px] p-2.5 hover:bg-surface-muted', current && 'bg-bg hover:bg-bg')}
            >
              <Avatar selected={current} />
              <span className="flex-1 text-sm font-semibold">{c.carer_ref}</span>
              <Badge variant={BAND_BADGE[c.band]} className="px-2 py-0.5">
                {BAND_LABEL[c.band]}
              </Badge>
            </Link>
          )
        })}
      </nav>
    </section>
  )
}

export function CarerHeader({ e }: { e: Explanation }) {
  return (
    <section aria-labelledby="carer" className="flex flex-wrap items-center gap-5 rounded-3xl bg-surface p-6">
      <Avatar selected large />
      <div className="flex flex-[1_1_240px] flex-col gap-1">
        <h1 id="carer" className="m-0 text-[28px] font-bold tracking-[-0.02em]">
          {e.carer_ref}
        </h1>
        <p className="m-0 text-sm text-muted-foreground">{profileLine(e)}</p>
      </div>
      <div className={cn('flex items-center gap-3.5 rounded-[18px] px-5 py-3.5', TILE[e.band])}>
        <div className="flex flex-col">
          <span className="text-xs font-medium">Attrition risk</span>
          <span className="text-[30px] font-bold tracking-[-0.02em]">{percent(e.risk)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[13px] font-semibold">{BAND_LABEL[e.band]}</span>
          <span className="text-xs">
            Rank {e.rank} of {e.of}
          </span>
        </div>
      </div>
    </section>
  )
}

export function KeySignals({ e }: { e: Explanation }) {
  return (
    <section aria-label="Key signals" className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
      {KEY_SIGNALS.map(({ feature, title }) => {
        const f = factorOf(e, feature)
        if (!f) return null
        // Text says what the colour means: only factors adding a point or more are red.
        const adds = f.points >= 1
        return (
          <div key={feature} className="flex flex-col gap-1.5 rounded-[20px] bg-surface px-5 py-[18px]">
            <span className="text-[13px] text-muted-foreground">{title}</span>
            <span className="text-[28px] font-bold tracking-[-0.02em]">{f.value}</span>
            <span className={cn('text-xs font-medium', adds ? 'text-high' : 'text-muted-foreground')}>
              {adds ? `Adds ${signedPoints(f.points)} pts · ` : ''}team {f.team_value}
            </span>
          </div>
        )
      })}
    </section>
  )
}

export function DriversPanel({ e }: { e: Explanation }) {
  const rows = driverRows(e.factors)
  return (
    <section aria-labelledby="drivers" className="flex flex-col gap-4 rounded-3xl bg-surface p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="drivers" className="m-0 text-lg font-semibold">
          What's driving this estimate
        </h2>
        <span className="text-[13px] text-muted-foreground">
          Baseline {percent(e.baseline_risk)} → {e.carer_ref} {percent(e.risk)}
        </span>
      </div>
      <div className="flex gap-[18px] text-xs text-soft">
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-[3px] bg-shap-up" aria-hidden="true" />
          Raises risk
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-[3px] bg-shap-down" aria-hidden="true" />
          Lowers risk
        </span>
      </div>
      <div className="overflow-x-auto">
        <ul
          aria-describedby="drivers-note"
          className="m-0 grid min-w-[560px] list-none grid-cols-[240px_1fr_1fr] items-center gap-y-3 p-0 text-sm"
        >
          {rows.map((r) => {
            const width = `${barWidth(r.points, rows)}%`
            const value = <span className="text-xs font-semibold">{signedPoints(r.points)}</span>
            const raises = r.points >= 0
            return (
              <li key={r.key} className="contents">
                <span className="text-note-text">
                  {r.label} {r.team && <span className="text-muted-foreground">(team {r.team})</span>}
                  <span className="sr-only">
                    , {raises ? 'raises' : 'lowers'} risk by {signedPoints(Math.abs(r.points)).slice(1)} points
                  </span>
                </span>
                {raises ? (
                  <>
                    <span className="h-[22px] border-r border-faint" aria-hidden="true" />
                    <span className="flex items-center gap-2" aria-hidden="true">
                      <span className="h-[22px] rounded-r-md bg-shap-up" style={{ width }} />
                      {value}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="flex items-center justify-end gap-2 border-r border-faint" aria-hidden="true">
                      {value}
                      <span className="h-[22px] rounded-l-md bg-shap-down" style={{ width }} />
                    </span>
                    <span aria-hidden="true" />
                  </>
                )}
              </li>
            )
          })}
        </ul>
      </div>
      <p id="drivers-note" className="m-0 text-xs text-muted-foreground">
        Values are percentage-point contributions (SHAP) to this carer's estimate. They add up from the baseline{' '}
        {percent(e.baseline_risk)} to {percent(e.risk)}. Explanations describe the model, not proven causes.
      </p>
    </section>
  )
}

const ACTION_ICON: Record<ActionKind, LucideIcon> = {
  route: MapPin,
  rota: CalendarDays,
  clients: Users,
  contract: FileText,
  development: GraduationCap,
  check_in: MessageSquare,
}

export function ActionsPanel({ actions, canSchedule }: { actions: SupportAction[]; canSchedule: boolean }) {
  return (
    <section aria-labelledby="actions" className="flex flex-col gap-3 rounded-3xl bg-surface p-6">
      <h2 id="actions" className="m-0 mb-1 text-lg font-semibold">
        Suggested supportive actions
      </h2>
      {actions.length === 0 && (
        <p className="m-0 text-sm text-muted-foreground">
          Nothing to suggest: no working condition the provider can change adds more than about 2 points.
        </p>
      )}
      {actions.map((a) => {
        const Icon = ACTION_ICON[a.kind]
        return (
          <div key={a.title} className="flex flex-wrap items-center gap-3.5 rounded-2xl bg-surface-muted px-4 py-3.5">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-surface" aria-hidden="true">
              <Icon size={18} strokeWidth={1.75} />
            </span>
            <span className="flex flex-[1_1_240px] flex-col gap-0.5">
              <span className="text-sm font-semibold">{a.title}</span>
              <span className="text-[13px] text-muted-foreground">{a.detail}</span>
            </span>
            {a.schedule && canSchedule && (
              <Link
                to="/schedule"
                className="flex h-[38px] items-center rounded-full bg-primary px-3.5 text-[13px] font-semibold text-primary-foreground hover:text-primary-foreground"
              >
                Open in schedule
              </Link>
            )}
          </div>
        )
      })}
    </section>
  )
}

export function UseNotice() {
  return (
    <p className="m-0 flex items-start gap-2.5 rounded-2xl bg-surface px-4 py-3.5 text-[13px] leading-normal text-soft">
      <Info size={18} strokeWidth={1.75} aria-hidden="true" className="mt-px shrink-0" />
      <span>
        A model estimate, not a judgement. Use it to offer support, never for performance or disciplinary decisions.
        Gradient boosting with SHAP explanations, trained on synthetic data.
      </span>
    </p>
  )
}

/** "Model card": the served model's identity, use notice and caveats, from the API. */
export function ModelCardPanel({ e }: { e: Explanation }) {
  return (
    <section id="model-card" aria-labelledby="model-card-title" className="flex flex-col gap-3 rounded-3xl bg-surface p-6">
      <h2 id="model-card-title" className="m-0 text-lg font-semibold">
        Model card
      </h2>
      <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-sm">
        <dt className="text-muted-foreground">Model</dt>
        <dd className="m-0 font-mono text-[13px]">{e.model.name}</dd>
        <dt className="text-muted-foreground">Version</dt>
        <dd className="m-0 font-mono text-[13px]">{e.model.version}</dd>
        <dt className="text-muted-foreground">Training data</dt>
        <dd className="m-0">{e.model.synthetic ? 'Synthetic carers only' : 'Provider records'}</dd>
        <dt className="text-muted-foreground">Support group</dt>
        <dd className="m-0">Top 20% by risk are suggested for a supportive check-in</dd>
      </dl>
      <p className="m-0 text-sm text-note-text">{e.use_notice}</p>
      <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-muted-foreground">
        {e.caveats.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <p className="m-0 text-xs text-muted-foreground">
        Full card in the repository: <span className="font-mono">docs/model-cards/attrition-model.md</span>
      </p>
    </section>
  )
}
