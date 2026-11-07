/** Care-note review: docs/design/screens/Review.dc.html (route /review/:noteId). */
import { useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'

import { ApiError } from '@/api/client'
import { PageContainer, PageHeader } from '@/app/AppShell'
import { useAuth } from '@/auth/auth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState, ErrorState, LoadingOverview } from '@/components/states/States'
import { useDecideNote, useNote, useQueue, type Flag, type Note } from '@/review/api'
import { SEVERITIES, SEVERITY_LABEL, type Severity } from '@/review/categories'
import { DecisionSupport } from '@/review/DecisionSupport'
import { clockTime, noteTitle, visitTime } from '@/review/format'
import { draftOf, toDecisions, type Draft } from '@/review/decisions'
import { ExtractionPanel, OriginalNote, Protocol } from '@/review/NoteView'
import { applyFilter, type QueueFilter } from '@/review/queue'
import { ReviewQueue } from '@/review/ReviewQueue'

const pendingFlags = (note: Note) => note.flags.filter((f) => f.review_status === 'pending')

function decisionError(err: unknown): string {
  if (err instanceof ApiError && err.status === 409)
    return 'Another reviewer has already decided this note. Reload to see the latest.'
  if (err instanceof ApiError && err.status === 422) return err.message
  const ref = err instanceof ApiError && err.reference ? ` Reference: ${err.reference}` : ''
  return `Couldn't log the decision.${ref}`
}

function worst(flags: Flag[]): Severity | undefined {
  return SEVERITIES.find((s) => flags.some((f) => f.severity === s))
}

const RISK_CHIP: Record<Severity, string> = {
  high: 'border-high-border',
  medium: 'border-medium-border',
  low: 'border-low-border',
}

function ReviewHeader({
  note,
  prev,
  next,
}: {
  note: Note | undefined
  prev: string | undefined
  next: string | undefined
}) {
  const navigate = useNavigate()
  const risk = note && worst(note.flags.filter((f) => f.review_status !== 'rejected'))
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface px-7 py-3.5">
      <div className="flex flex-wrap items-center gap-2.5 text-sm">
        <Link to="/review" className="text-muted-foreground">
          Review queue
        </Link>
        <span className="text-faint" aria-hidden="true">
          /
        </span>
        <span className="font-semibold">{note ? `${note.client_ref} · Visit note` : '…'}</span>
        {risk && (
          <Badge variant={risk} className={`rounded-sm border py-0.5 ${RISK_CHIP[risk]}`}>
            {SEVERITY_LABEL[risk]} risk
          </Badge>
        )}
        <Badge variant="demo" className="text-xs">
          Demo data · synthetic
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        {(
          [
            ['Previous', prev],
            ['Next note', next],
          ] as const
        ).map(([label, id]) => (
          <Button
            key={label}
            type="button"
            variant="outline"
            disabled={!id}
            onClick={() => id && navigate(`/review/${id}`)}
            className="h-10 cursor-pointer rounded-full px-4 text-sm font-medium"
          >
            {label}
          </Button>
        ))}
      </div>
    </header>
  )
}

/** One note's review. Keyed by note id, so staged edits reset when you move on. */
function NoteReview({ note, nextId }: { note: Note; nextId: string | undefined }) {
  const { can } = useAuth()
  const navigate = useNavigate()
  const decide = useDecideNote(note.id)
  const pending = pendingFlags(note)
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() =>
    Object.fromEntries(pending.map((f) => [f.id, draftOf(f)])),
  )
  const [editing, setEditing] = useState(false)
  const canDecide = can('review.decide') && note.review_required
  const kept = pending.filter((f) => !drafts[f.id]?.reject)
  const hasHigh = kept.some((f) => (drafts[f.id]?.severity ?? f.severity) === 'high')
  const top = [...note.flags]
    .filter((f) => f.review_status !== 'rejected')
    .sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity))[0]

  const submit = (rejectAll: boolean, escalate: boolean) =>
    decide.mutate(
      { decisions: toDecisions(pending, drafts, rejectAll), escalate },
      { onSuccess: () => navigate(nextId ? `/review/${nextId}` : '/review') },
    )

  return (
    <>
      <main className="box-border flex min-w-0 flex-[999_1_520px] flex-col gap-5 px-8 pt-7 pb-10 max-sm:px-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="m-0 text-[28px] font-bold tracking-[-0.02em]">
            {noteTitle(top?.category, note.visit_time)}
          </h1>
          <p className="m-0 text-sm text-muted-foreground">
            Carer {note.carer_ref} · {visitTime(note.visit_time)} · Submitted {clockTime(note.created_at)}
          </p>
        </div>
        <OriginalNote note={note} />
        <ExtractionPanel
          note={note}
          drafts={drafts}
          editing={editing}
          canDecide={canDecide}
          busy={decide.isPending}
          onDraft={(id, d) => setDrafts((all) => ({ ...all, [id]: d }))}
          onToggleEdit={() => setEditing((e) => !e)}
          onReject={() => submit(true, false)}
          onApprove={() => submit(false, false)}
          error={decide.error ? decisionError(decide.error) : null}
        />
        <Protocol category={top?.category} />
      </main>
      <DecisionSupport
        note={note}
        canDecide={canDecide}
        hasHigh={hasHigh}
        busy={decide.isPending}
        onEscalate={() => submit(false, true)}
        onApprove={() => submit(false, false)}
      />
    </>
  )
}

function NoteSkeleton() {
  return (
    <main aria-busy="true" className="flex min-w-0 flex-[999_1_520px] flex-col gap-5 px-8 pt-7">
      <span className="sr-only">Loading care note</span>
      <Skeleton className="h-8 w-2/3 rounded-lg bg-skeleton-strong" />
      <Skeleton className="h-40 rounded-2xl" />
      <Skeleton className="h-72 rounded-2xl" />
    </main>
  )
}

export function ReviewPage() {
  const { noteId } = useParams()
  const [filter, setFilter] = useState<QueueFilter>('all')
  const [now] = useState(() => new Date())
  const queue = useQueue()
  const note = useNote(noteId)
  const items = useMemo(() => applyFilter(queue.data ?? [], filter), [queue.data, filter])

  if (queue.isPending)
    return (
      <PageContainer>
        <PageHeader title="Review" />
        <div className="flex min-h-[420px]">
          <LoadingOverview label="Loading review queue" />
        </div>
      </PageContainer>
    )
  if (queue.isError)
    return (
      <PageContainer>
        <PageHeader title="Review" />
        <div className="flex min-h-[420px]">
          <ErrorState
            title="Couldn't load the review queue"
            message="The care notes waiting for review couldn't be fetched. Nothing has been decided or changed."
            onRetry={() => void queue.refetch()}
            secondary={{ label: 'Back to overview', to: '/' }}
            reference={queue.error instanceof ApiError ? queue.error.reference : null}
          />
        </div>
      </PageContainer>
    )
  if (!noteId) {
    const first = items[0] ?? queue.data[0]
    if (first) return <Navigate to={`/review/${first.note_id}`} replace />
    return (
      <PageContainer>
        <PageHeader title="Review" />
        <div className="flex min-h-[420px]">
          <EmptyState />
        </div>
      </PageContainer>
    )
  }

  const at = items.findIndex((i) => i.note_id === noteId)
  const prev = at > 0 ? items[at - 1]?.note_id : undefined
  const next = at >= 0 ? items[at + 1]?.note_id : items[0]?.note_id
  // After deciding, move to the next note still waiting (not the one just decided).
  const nextAfterDecision = items.find((i, idx) => i.note_id !== noteId && (at < 0 || idx > at))?.note_id
    ?? items.find((i) => i.note_id !== noteId)?.note_id

  return (
    <>
      <ReviewHeader note={note.data} prev={prev} next={next} />
      <div className="flex flex-1 flex-wrap">
        <ReviewQueue
          items={items}
          total={queue.data.length}
          filter={filter}
          onFilter={setFilter}
          currentId={noteId}
          now={now}
        />
        {note.isPending ? (
          <NoteSkeleton />
        ) : note.isError ? (
          <main className="flex min-w-0 flex-[999_1_520px] p-8">
            <ErrorState
              title={note.error instanceof ApiError && note.error.status === 404 ? 'Note not found' : "Couldn't load this note"}
              message="It may have been removed, or the link is wrong. The rest of the queue is unaffected."
              onRetry={() => void note.refetch()}
              secondary={{ label: 'Back to queue', to: '/review' }}
              reference={note.error instanceof ApiError ? note.error.reference : null}
            />
          </main>
        ) : (
          <NoteReview key={note.data.id} note={note.data} nextId={nextAfterDecision} />
        )}
      </div>
    </>
  )
}
