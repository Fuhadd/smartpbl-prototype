/** Overview panels, rebuilt from docs/design/screens/Main.dc.html. */
import {
  Bandage,
  Brain,
  ChevronRight,
  Clock,
  Pill,
  Shield,
  Sparkle,
  TriangleAlert,
  UserRoundCheck,
  Utensils,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import type { Category } from '@/review/categories'
import { cn } from '@/lib/utils'

import type { Overview } from './api'
import { attentionRows, delta, percent, type AttentionIcon, type AttentionTone } from './attention'

function PanelTitle({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="m-0 text-lg font-semibold">
      {children}
    </h2>
  )
}

const panelId = (label: string) => `panel-${label.toLowerCase().replaceAll(/[^a-z]+/g, '-')}`

// --- Today at a glance ---------------------------------------------------------------------

function Tile({ to, label, value, note, noteClass }: {
  to: string
  label: string
  value: ReactNode
  note: string
  noteClass: string
}) {
  return (
    <Link to={to} className="flex flex-col gap-1.5 rounded-[18px] bg-surface-muted px-6 py-5 hover:bg-bg">
      <span className="text-[13px] font-medium text-muted-foreground">{label}</span>
      <span className="text-4xl font-bold tracking-[-0.02em]">{value}</span>
      <span className={cn('text-[13px] font-medium', noteClass)}>{note}</span>
    </Link>
  )
}

export function AtAGlance({ data }: { data: Overview }) {
  const { review, schedule, workforce } = data
  return (
    <section
      aria-label="Today at a glance"
      className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-2 rounded-3xl bg-surface p-2"
    >
      <Tile
        to="/review"
        label="Flags awaiting review"
        value={review.awaiting_flags}
        note={review.awaiting_high ? `${review.awaiting_high} high severity` : 'None high severity'}
        noteClass={review.awaiting_high ? 'text-high' : 'text-muted-foreground'}
      />
      <Tile
        to="/schedule"
        label="Unassigned visits"
        value={schedule ? schedule.unassigned : '—'}
        note={schedule ? 'Re-optimise schedule' : 'No rota saved yet'}
        noteClass="text-medium"
      />
      <Tile
        to="/schedule"
        label="Visits today"
        value={schedule ? schedule.visits : '—'}
        note={schedule ? `${schedule.carers_on_shift} carers on shift` : 'No rota saved yet'}
        noteClass="text-muted-foreground"
      />
      <Tile
        to="/workforce"
        label="Carers at elevated risk"
        value={workforce ? workforce.elevated : '—'}
        note="View workforce"
        noteClass="text-ai-text"
      />
    </section>
  )
}

// --- Needs attention ---------------------------------------------------------------------

const ICON: Record<AttentionIcon, LucideIcon> = {
  falls: TriangleAlert,
  safeguarding: Shield,
  medication: Pill,
  nutrition_hydration: Utensils,
  skin_integrity: Bandage,
  mood_behaviour: Brain,
  missed_late_visit: Clock,
  extraction_failed: TriangleAlert,
  unassigned: Clock,
  check_in: UserRoundCheck,
}

const TONE: Record<AttentionTone, string> = {
  high: 'bg-high-bg text-high',
  medium: 'bg-medium-bg text-medium',
  low: 'bg-low-bg text-low',
  schedule: 'bg-medium-bg text-medium',
  workforce: 'bg-ai-bg-strong text-ai-text',
}

export function NeedsAttention({ data }: { data: Overview }) {
  const rows = attentionRows(data)
  const id = panelId('Needs attention')
  return (
    <section
      aria-labelledby={id}
      className="flex min-w-0 flex-[999_1_520px] flex-col gap-4 rounded-3xl bg-surface p-6"
    >
      <div className="flex items-center justify-between">
        <PanelTitle id={id}>Needs attention</PanelTitle>
        <Link to="/review" className="flex items-center gap-1.5 text-[13px] font-medium">
          See all
          <span className="flex size-[18px] items-center justify-center rounded-full bg-primary text-primary-foreground">
            <ChevronRight size={12} strokeWidth={2.5} aria-hidden="true" />
          </span>
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="m-0 rounded-[18px] bg-surface-muted px-4 py-5 text-sm text-muted-foreground">
          Nothing needs attention right now. New flags and unassigned visits appear here.
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-4 p-0">
          {rows.map((r) => {
            const Icon = ICON[r.icon]
            return (
              <li key={r.key}>
                <Link to={r.to} className="flex items-center gap-4 rounded-[18px] bg-surface-muted px-4 py-3.5 hover:bg-bg">
                  <span className={cn('flex size-11 flex-[0_0_44px] items-center justify-center rounded-[14px]', TONE[r.tone])}>
                    <Icon size={20} strokeWidth={1.75} aria-hidden="true" />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-[15px] font-semibold">{r.title}</span>
                    <span className="truncate text-[13px] text-muted-foreground">{r.detail}</span>
                  </span>
                  <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', TONE[r.tone])}>{r.badge}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// --- Flags by category -------------------------------------------------------------------

/** Bar labels exactly as Main.dc.html (shorter than the review screen's labels). */
const BAR_LABEL: Record<Category, string> = {
  nutrition_hydration: 'Nutrition / hydration',
  mood_behaviour: 'Mood / behaviour',
  falls: 'Falls',
  medication: 'Medication',
  skin_integrity: 'Skin integrity',
  safeguarding: 'Safeguarding',
  missed_late_visit: 'Missed / late visit',
}

export function FlagsByCategory({ data }: { data: Overview }) {
  const { counts, window_days } = data.flags_by_category
  const max = Math.max(1, ...counts.map((c) => c.count))
  const id = panelId('Flags by category')
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3.5 rounded-3xl bg-surface p-6">
      <div className="flex items-baseline justify-between">
        <PanelTitle id={id}>Flags by category</PanelTitle>
        <span className="text-[13px] text-muted-foreground">Last {window_days} days</span>
      </div>
      {counts.length === 0 ? (
        <p className="m-0 text-sm text-muted-foreground">No flags in the last {window_days} days.</p>
      ) : (
        <ul className="m-0 grid list-none grid-cols-[132px_1fr_28px] items-center gap-x-3 gap-y-2.5 p-0 text-[13px]">
          {counts.map((c) => (
            <li key={c.category} className="contents" aria-label={`${BAR_LABEL[c.category]}: ${c.count}`}>
              <span className="text-soft" aria-hidden="true">{BAR_LABEL[c.category]}</span>
              <span className="h-2 rounded-full bg-track" aria-hidden="true">
                <span className="block h-2 rounded-full bg-primary" style={{ width: `${(c.count / max) * 100}%` }} />
              </span>
              <span className="text-right font-semibold" aria-hidden="true">{c.count}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// --- Today's schedule --------------------------------------------------------------------

const PRESET_LABEL = { travel: 'Travel', balanced: 'Balanced', continuity: 'Continuity', custom: 'Custom' } as const

function Stat({ label, value, change }: { label: string; value: string; change: ReturnType<typeof delta> }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl bg-surface-muted p-4">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl font-bold">{value}</span>
      {change && (
        <span className={cn('text-xs font-medium', change.better ? 'text-success' : 'text-muted-foreground')}>
          {change.text}
        </span>
      )}
    </div>
  )
}

export function TodaysSchedule({ data }: { data: Overview }) {
  const s = data.schedule
  const id = panelId("Today's schedule")
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3.5 rounded-3xl bg-surface p-6">
      <div className="flex items-center justify-between">
        <PanelTitle id={id}>Today's schedule</PanelTitle>
        {s && (
          <span className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
            {PRESET_LABEL[s.preset]}
          </span>
        )}
      </div>
      {s ? (
        <div className="grid grid-cols-2 gap-2.5">
          <Stat label="Total travel" value={`${s.travel_h.toFixed(1)} h`}
            change={delta(s.travel_h, s.baseline?.travel_h, 'h', true)} />
          <Stat label="Continuity of care" value={percent(s.familiar_pct)}
            change={delta(s.familiar_pct, s.baseline?.familiar_pct, 'pts', false)} />
        </div>
      ) : (
        <p className="m-0 text-sm text-muted-foreground">No rota saved yet. Run the optimiser from the schedule screen.</p>
      )}
      <Link
        to="/schedule"
        className="flex h-11 items-center justify-center rounded-full border border-border text-sm font-semibold hover:bg-surface-muted"
      >
        Open schedule
      </Link>
    </section>
  )
}

// --- AI pipeline health ------------------------------------------------------------------

export function PipelineHealth({ data }: { data: Overview }) {
  const p = data.pipeline
  const id = panelId('AI pipeline health')
  const rows: [string, string][] = [
    ['Schema-valid outputs', percent(p.schema_valid_rate)],
    ['Evidence grounded', percent(p.grounded_rate)],
    ['Median latency', p.median_latency_ms == null ? '—' : `${(p.median_latency_ms / 1000).toFixed(1)} s`],
    // Ollama runs on the provider's own machine: no note text leaves it.
    ['Model', p.model_name ? `${p.model_name} · local` : '—'],
  ]
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-3xl bg-surface p-6">
      <div className="flex items-center gap-2">
        <Sparkle size={18} strokeWidth={1.75} className="text-ai" aria-hidden="true" />
        <PanelTitle id={id}>AI pipeline health</PanelTitle>
      </div>
      <dl className="m-0 flex flex-col gap-2.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="m-0 font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
