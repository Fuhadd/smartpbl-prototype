/** Temporary stand-in for screens later Tier 5 steps build. Not a design screen: removed
 * as each step lands (tracked in docs/learning/BACKLOG.md). */
export function PendingStep({ step, what }: { step: string; what: string }) {
  return (
    <section className="rounded-3xl border border-dashed border-border bg-surface p-8 text-center">
      <p className="m-0 text-sm text-muted-foreground">
        {what} arrive in Step {step}.
      </p>
    </section>
  )
}
