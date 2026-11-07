/** The right column of Review.dc.html: why, safety checks, routing, decision buttons. */
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import type { Note } from './api'
import { whyReview } from './format'
import { redactedTypes, sentenceCase } from './noteText'

const CARD = 'flex flex-col rounded-2xl bg-surface p-[18px]'
const H = 'm-0 text-[15px] font-semibold'

function Check({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[13px]">
      <span className="text-soft">{label}</span>
      <span
        className={cn(
          'rounded-sm px-2 py-0.5 text-xs font-semibold',
          ok ? 'bg-success-bg text-success' : 'bg-high-bg text-high',
        )}
      >
        {value}
      </span>
    </div>
  )
}

type StepState = 'done' | 'current' | 'required' | 'escalated' | 'idle' | 'failed'
const STEP_CHIP: Partial<Record<StepState, { text: string; className: string }>> = {
  done: { text: 'Done', className: 'border-success-border text-success' },
  current: { text: 'Current', className: 'border-low-border text-low' },
  required: { text: 'Required', className: 'border-medium-border text-medium' },
  escalated: { text: 'Escalated', className: 'border-medium-border text-medium' },
  failed: { text: 'Failed', className: 'border-high-border text-high' },
}
const STEP_DOT: Record<StepState, string> = {
  done: 'bg-dot-done',
  current: 'bg-primary',
  required: 'bg-dot-idle',
  escalated: 'bg-dot-medium',
  idle: 'bg-dot-idle',
  failed: 'bg-dot-high',
}

function Step({ label, state }: { label: string; state: StepState }) {
  const chip = STEP_CHIP[state]
  return (
    <div
      className={cn(
        'flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-[13px]',
        state === 'current' ? 'border-primary font-semibold' : 'border-border',
        state === 'idle' && 'text-muted-foreground',
      )}
    >
      <span aria-hidden="true" className={cn('size-2 rounded-full', STEP_DOT[state])} />
      <span className="flex-1">{label}</span>
      {chip && <span className={cn('rounded-sm border px-1.5 py-px text-[11px] font-semibold', chip.className)}>{chip.text}</span>}
    </div>
  )
}

export function DecisionSupport({
  note,
  canDecide,
  hasHigh,
  busy,
  onEscalate,
  onApprove,
}: {
  note: Note
  canDecide: boolean
  hasHigh: boolean
  busy: boolean
  onEscalate: () => void
  onApprove: () => void
}) {
  const llm = note.extractions.find((e) => e.source === 'llm')
  const failed = llm?.status !== 'ok'
  const live = note.flags.filter((f) => f.review_status !== 'rejected')
  const grounded = live.filter((f) => f.grounding_status !== 'ungrounded').length
  const { words } = redactedTypes(note.redacted_text)
  const { because, confidence } = whyReview(
    note.flags.filter((f) => f.review_status === 'pending'),
    failed,
  )
  const decided = !note.review_required

  let because_: ReactNode = 'No flag needed a person to review it.'
  if (because.length)
    because_ = (
      <>
        Routed because <strong className="text-text">{because.join('; ')}</strong>.
      </>
    )

  return (
    <aside
      aria-label="Decision support"
      className="box-border flex max-w-[360px] min-w-0 flex-[1_1_300px] flex-col gap-4 py-7 pr-7 pb-10 max-lg:max-w-none max-lg:px-8"
    >
      {!decided && (
        <section aria-labelledby="why" className={cn(CARD, 'gap-2.5')}>
          <h2 id="why" className={H}>
            Why this needs review
          </h2>
          <p className="m-0 text-[13px] leading-[1.6] text-muted-foreground">
            {because_} {confidence}
          </p>
        </section>
      )}

      <section aria-labelledby="checks" className={cn(CARD, 'gap-3')}>
        <h2 id="checks" className={H}>
          Safety checks
        </h2>
        <Check label="Evidence found in note" ok={grounded === live.length} value={`${grounded} / ${live.length}`} />
        <Check label="Schema validation" ok={!failed} value={failed ? 'Failed' : 'Passed'} />
        <Check
          label="Identifiers redacted before AI"
          ok
          value={words.length ? sentenceCase(words) : 'None found'}
        />
        {/* Inference runs on a local Ollama model (ADR-001): note text never leaves the host. */}
        <Check label="Data left this device" ok value="No" />
      </section>

      <section aria-labelledby="route" className={cn(CARD, 'gap-2')}>
        <h2 id="route" className={cn(H, 'mb-1')}>
          Approval routing
        </h2>
        <Step label="AI extraction" state={failed ? 'failed' : 'done'} />
        <Step label="Coordinator review" state={decided ? 'done' : 'current'} />
        <Step
          label="Care manager sign-off"
          state={note.escalated_at ? 'escalated' : hasHigh && !decided ? 'required' : 'idle'}
        />
        <Step label="Written to audit log" state={decided ? 'done' : 'idle'} />
      </section>

      {canDecide && (
        <>
          {hasHigh && (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={onEscalate}
              className="h-[46px] cursor-pointer rounded-lg text-sm font-semibold"
            >
              Escalate to care manager
            </Button>
          )}
          <Button
            type="button"
            disabled={busy}
            onClick={onApprove}
            className="h-[46px] cursor-pointer rounded-lg text-sm font-semibold"
          >
            Approve and log decision
          </Button>
        </>
      )}
    </aside>
  )
}
