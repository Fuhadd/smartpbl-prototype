/** The centre column of Review.dc.html: original note, AI extraction, protocol. */
import { Check, Pencil, ShieldCheck, Sparkle, TriangleAlert, X } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import type { Flag, Note } from './api'
import { CATEGORIES, CATEGORY, SEVERITIES, SEVERITY_LABEL, type Category, type Severity } from './categories'
import type { Draft } from './decisions'
import { medicationText, modelLine } from './format'
import { redactedTypes, segmentNote, type Piece } from './noteText'
import { PROTOCOLS } from './protocols'

const SECTION = 'overflow-hidden rounded-2xl border bg-surface'
const SECTION_HEAD = 'flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3'
const EYEBROW = 'm-0 text-xs font-semibold tracking-[0.06em]'

function Pieces({ pieces }: { pieces: Piece[] }) {
  return pieces.map((p, i) =>
    p.kind === 'text' ? (
      <span key={i}>{p.text}</span>
    ) : p.kind === 'redacted' ? (
      <span key={i} className="rounded-[4px] bg-bg px-1.5 py-px font-mono text-[13px]">
        [{p.label}]
      </span>
    ) : (
      <mark
        key={i}
        className="rounded-[4px] px-1 py-0.5 text-text"
        style={{ background: CATEGORY[p.category].highlight }}
        title={CATEGORY[p.category].label}
      >
        <Pieces pieces={p.pieces} />
      </mark>
    ),
  )
}

export function OriginalNote({ note }: { note: Note }) {
  const spans = note.flags
    .filter((f) => f.review_status !== 'rejected' && f.span_start != null && f.span_end != null)
    .map((f) => ({ start: f.span_start!, end: f.span_end!, category: f.category }))
  const { count } = redactedTypes(note.redacted_text)
  return (
    <section aria-labelledby="orig" className={cn(SECTION, 'border-border')}>
      <div className={cn(SECTION_HEAD, 'border-border bg-surface-muted')}>
        <h2 id="orig" className={cn(EYEBROW, 'text-muted-foreground')}>
          ORIGINAL CARE NOTE
        </h2>
        <span className="flex items-center gap-1.5 text-xs font-medium text-success">
          <ShieldCheck size={14} strokeWidth={1.75} aria-hidden="true" />
          {count} {count === 1 ? 'identifier' : 'identifiers'} redacted
        </span>
      </div>
      <p className="m-0 p-5 text-[15px] leading-[1.75] text-note-text">
        <Pieces pieces={segmentNote(note.redacted_text, spans)} />
      </p>
    </section>
  )
}

function Grounding({ status }: { status: Flag['grounding_status'] }) {
  if (status === 'ungrounded')
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-high">
        <TriangleAlert size={14} strokeWidth={1.75} aria-hidden="true" />
        Not found in note
      </span>
    )
  return (
    <span className="flex items-center gap-1 text-xs font-medium text-success">
      <Check size={14} strokeWidth={1.75} aria-hidden="true" />
      {status === 'fuzzy' ? 'Grounded (approximate)' : 'Grounded'}
    </span>
  )
}

const SELECT = 'h-9 rounded-lg border border-border bg-surface px-2 text-sm'

function FlagCard({
  flag,
  draft,
  editing,
  onDraft,
}: {
  flag: Flag
  draft: Draft | undefined
  editing: boolean
  onDraft: (d: Draft) => void
}) {
  const shown = draft ?? { reject: false, category: flag.category, severity: flag.severity, evidence: flag.evidence }
  const decided = flag.review_status !== 'pending' && flag.review_status !== 'auto_accepted'
  return (
    <div
      className={cn(
        'flex flex-col gap-2.5 rounded-[14px] border border-border px-4 py-3.5',
        shown.reject && 'opacity-60',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <span aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: CATEGORY[shown.category].swatch }} />
          {CATEGORY[shown.category].label}
        </span>
        <Badge variant={shown.severity} className="py-0.5">
          {SEVERITY_LABEL[shown.severity]}
        </Badge>
        {shown.reject && <Badge variant="outline">Will be rejected</Badge>}
        {decided && <Badge variant="outline">{flag.review_status}</Badge>}
        <span className="ml-auto text-xs text-muted-foreground">Confidence {flag.confidence.toFixed(2)}</span>
        <Grounding status={flag.grounding_status} />
      </div>
      {editing && draft ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <label className="flex items-center gap-2 text-[13px]">
              Category
              <select
                className={SELECT}
                value={draft.category}
                onChange={(e) => onDraft({ ...draft, category: e.target.value as Category })}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY[c].label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-[13px]">
              Severity
              <select
                className={SELECT}
                value={draft.severity}
                onChange={(e) => onDraft({ ...draft, severity: e.target.value as Severity })}
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {SEVERITY_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="ml-auto cursor-pointer"
              onClick={() => onDraft({ ...draft, reject: !draft.reject })}
            >
              {draft.reject ? 'Keep flag' : 'Reject flag'}
            </Button>
          </div>
          <label className="flex flex-col gap-1 text-[13px]">
            Evidence (must be a quote from the note)
            <textarea
              className="min-h-16 rounded-[10px] border border-border bg-surface-muted px-3 py-2.5 text-sm text-soft"
              value={draft.evidence}
              onChange={(e) => onDraft({ ...draft, evidence: e.target.value })}
            />
          </label>
        </div>
      ) : (
        <p className="m-0 rounded-[10px] bg-surface-muted px-3 py-2.5 text-sm text-soft">“{shown.evidence}”</p>
      )}
    </div>
  )
}

function Tile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-surface-muted px-3.5 py-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  )
}

export function ExtractionPanel({
  note,
  drafts,
  editing,
  canDecide,
  busy,
  onDraft,
  onToggleEdit,
  onReject,
  onApprove,
  error,
}: {
  note: Note
  drafts: Record<string, Draft>
  editing: boolean
  canDecide: boolean
  busy: boolean
  onDraft: (id: string, d: Draft) => void
  onToggleEdit: () => void
  onReject: () => void
  onApprove: () => void
  error: string | null
}) {
  const llm = note.extractions.find((e) => e.source === 'llm')
  const failed = llm?.status === 'failed'
  const result = llm?.extraction as { medication_status?: string; follow_up_required?: boolean } | null | undefined
  const flags = note.flags.filter((f) => f.review_status !== 'rejected' || drafts[f.id])
  return (
    <section aria-labelledby="extr" className={cn(SECTION, 'border-ai-border')}>
      <div className={cn(SECTION_HEAD, 'border-ai-divider bg-ai-bg')}>
        <h2 id="extr" className={cn(EYEBROW, 'flex items-center gap-2 text-ai-text')}>
          <Sparkle size={14} strokeWidth={1.75} aria-hidden="true" className="text-ai" />
          AI EXTRACTION
        </h2>
        <span className="text-xs text-muted-foreground">{modelLine(llm)}</span>
      </div>
      <div className="flex flex-col gap-3 px-5 py-4">
        {failed && (
          <p role="status" className="m-0 rounded-[10px] bg-medium-bg px-3 py-2.5 text-sm text-medium">
            The AI extraction failed after {llm?.attempts ?? 1} attempts. Flags below come from the rules baseline.
          </p>
        )}
        {flags.map((f) => (
          <FlagCard key={f.id} flag={f} draft={drafts[f.id]} editing={editing} onDraft={(d) => onDraft(f.id, d)} />
        ))}
        {!flags.length && <p className="m-0 text-sm text-muted-foreground">No risk flags in this note.</p>}
        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-2.5 text-[13px]">
          <Tile label="Medication" value={medicationText(result?.medication_status)} />
          <Tile
            label="Follow-up required"
            value={result?.follow_up_required == null ? 'Not available' : result.follow_up_required ? 'Yes' : 'No'}
          />
        </div>
      </div>
      {canDecide && (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-3.5">
          <Button
            type="button"
            variant="outline"
            aria-pressed={editing}
            onClick={onToggleEdit}
            className="h-10 cursor-pointer rounded-[10px] px-3.5 text-sm font-medium"
          >
            <Pencil strokeWidth={1.75} aria-hidden="true" />
            Edit
          </Button>
          <span className="flex-1" />
          {error && (
            <span role="alert" className="text-[13px] font-medium text-high">
              {error}
            </span>
          )}
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            onClick={onReject}
            className="h-10 cursor-pointer rounded-[10px] px-3.5 text-sm font-medium text-soft"
          >
            <X strokeWidth={1.75} aria-hidden="true" />
            Reject
          </Button>
          <Button
            type="button"
            disabled={busy}
            onClick={onApprove}
            className="h-10 cursor-pointer rounded-[10px] px-4 text-sm font-semibold"
          >
            <Check strokeWidth={1.75} aria-hidden="true" />
            Approve extraction
          </Button>
        </div>
      )}
    </section>
  )
}

export function Protocol({ category }: { category: Category | undefined }) {
  const text = category ? PROTOCOLS[category] : undefined
  if (!category || !text) return null
  return (
    <section aria-labelledby="proto" className={cn(SECTION, 'border-border')}>
      <div className="border-b border-border bg-surface-muted px-5 py-3">
        <h2 id="proto" className={cn(EYEBROW, 'text-muted-foreground')}>
          PBL {CATEGORY[category].short.toUpperCase()} PROTOCOL
        </h2>
      </div>
      <p className="m-0 px-5 py-4 text-sm leading-[1.6] text-soft">{text}</p>
    </section>
  )
}
