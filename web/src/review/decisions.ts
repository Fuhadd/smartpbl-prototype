/** Staged review decisions -> the API's all-or-nothing decision list. */
import type { Flag, FlagDecision } from './api'
import type { Category, Severity } from './categories'

/** What the reviewer has staged for one flag before logging the decision. */
export type Draft = { reject: boolean; category: Category; severity: Severity; evidence: string }

export function draftOf(f: Flag): Draft {
  return { reject: false, category: f.category, severity: f.severity, evidence: f.evidence }
}

/** Approve unchanged flags, edit changed ones (only the changed fields), reject the rest. */
export function toDecisions(pending: Flag[], drafts: Record<string, Draft>, rejectAll: boolean): FlagDecision[] {
  return pending.map((f) => {
    const d = drafts[f.id] ?? draftOf(f)
    if (rejectAll || d.reject) return { flag_id: f.id, action: 'reject' }
    const edit: NonNullable<FlagDecision['edit']> = {}
    if (d.category !== f.category) edit.category = d.category
    if (d.severity !== f.severity) edit.severity = d.severity
    if (d.evidence.trim() !== f.evidence) edit.evidence = d.evidence.trim()
    return Object.keys(edit).length ? { flag_id: f.id, action: 'edit', edit } : { flag_id: f.id, action: 'approve' }
  })
}
