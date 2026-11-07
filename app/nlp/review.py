"""Human review of risk flags: approve, edit or reject, with a stored before/after diff.

Each decision, in one transaction:
  1. locks the flag row (SELECT ... FOR UPDATE), so two reviewers can't both decide it;
  2. applies the change to `risk_flags` (the current view);
  3. stores a `review_decisions` row with before, after and a field-level diff;
  4. appends a `review_decision` audit event.

Edited evidence must still be a quote from the (redacted) note: it is re-grounded, and
the stored evidence is the matched span of the note, not the reviewer's typed text.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.log import record
from app.audit.models import EventType
from app.nlp.ground import ground
from app.nlp.models import (
    CareNoteRecord,
    ReviewAction,
    ReviewDecisionRecord,
    ReviewStatus,
    RiskFlagRecord,
)
from app.nlp.schemas import RiskCategory, Severity

# Decided flags are final in this prototype; correcting a decision is future work.
REVIEWABLE = frozenset({ReviewStatus.PENDING, ReviewStatus.AUTO_ACCEPTED})
_RESULT = {
    ReviewAction.APPROVE: ReviewStatus.APPROVED,
    ReviewAction.EDIT: ReviewStatus.EDITED,
    ReviewAction.REJECT: ReviewStatus.REJECTED,
}
_SNAPSHOT_FIELDS = (
    "category",
    "severity",
    "evidence",
    "span_start",
    "span_end",
    "grounding_status",
    "grounding_score",
    "review_status",
)


class FlagEdit(BaseModel):
    """Fields a reviewer may change. Omitted fields keep their current value."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: RiskCategory | None = None
    severity: Severity | None = None
    evidence: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def _not_empty(self) -> "FlagEdit":
        if not self.model_fields_set:
            raise ValueError("edit must change at least one of category, severity, evidence")
        return self


class FlagNotFoundError(LookupError):
    pass


class AlreadyReviewedError(Exception):
    def __init__(self, status: ReviewStatus) -> None:
        super().__init__(f"flag already reviewed ({status.value})")
        self.status = status


class InvalidEditError(ValueError):
    pass


def _snapshot(flag: RiskFlagRecord) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in _SNAPSHOT_FIELDS:
        value = getattr(flag, name)
        out[name] = value.value if hasattr(value, "value") else value
    return out


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {k: {"before": before[k], "after": after[k]} for k in before if before[k] != after[k]}


def _apply_edit(flag: RiskFlagRecord, note: CareNoteRecord, edit: FlagEdit) -> None:
    if edit.category is not None:
        flag.category = edit.category
    if edit.severity is not None:
        flag.severity = edit.severity
    if edit.evidence is not None:
        g = ground(edit.evidence, note.redacted_text)
        if not g.grounded or g.start is None or g.end is None:
            raise InvalidEditError("edited evidence must be a quote from the (redacted) note")
        flag.evidence = note.redacted_text[g.start : g.end]
        flag.span_start, flag.span_end = g.start, g.end
        flag.grounding_status, flag.grounding_score = g.status, g.score


def review_flag(
    session: Session,
    flag_id: UUID,
    *,
    reviewer: str,
    action: ReviewAction,
    edit: FlagEdit | None = None,
    comment: str | None = None,
) -> ReviewDecisionRecord:
    """Apply one review decision. Adds rows to the session; the caller commits."""
    if (action is ReviewAction.EDIT) != (edit is not None):
        raise InvalidEditError("an edit is required for action 'edit' and only for it")

    flag = session.get(RiskFlagRecord, flag_id, with_for_update=True)
    if flag is None:
        raise FlagNotFoundError(str(flag_id))
    if flag.review_status not in REVIEWABLE:
        raise AlreadyReviewedError(flag.review_status)

    note = flag.note
    before = _snapshot(flag)
    if edit is not None:
        _apply_edit(flag, note, edit)
    flag.review_status = _RESULT[action]
    after = _snapshot(flag)
    diff = _diff(before, after)
    if action is ReviewAction.EDIT and set(diff) == {"review_status"}:
        raise InvalidEditError("edit changes nothing; use 'approve' instead")

    decision = ReviewDecisionRecord(
        flag_id=flag.id,
        reviewer=reviewer,
        action=action,
        before=before,
        after=after,
        diff=diff,
        comment=comment,
    )
    session.add(decision)
    session.flush()

    pending = session.scalar(
        select(RiskFlagRecord.id)
        .where(RiskFlagRecord.note_id == note.id)
        .where(RiskFlagRecord.review_status == ReviewStatus.PENDING)
        .limit(1)
    )
    note.review_required = pending is not None

    record(
        session,
        EventType.REVIEW_DECISION,
        actor=f"user:{reviewer}",
        note_id=note.id,
        output={
            "flag_id": str(flag.id),
            "decision_id": str(decision.id),
            "action": action.value,
            "diff": diff,
            # Free-text comments may contain personal data: kept out of the permanent log.
            "has_comment": comment is not None,
            "note_review_required": note.review_required,
        },
    )
    return decision


# --- Note-level decisions (Step 5.2) ---------------------------------------------------


class FlagDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_id: UUID
    action: ReviewAction
    edit: FlagEdit | None = None


class NoteNotFoundError(LookupError):
    pass


class NoteDecisionError(ValueError):
    """The decision set doesn't fit the note (incomplete, duplicated, or bad escalation)."""


_KEPT = frozenset({ReviewStatus.APPROVED, ReviewStatus.EDITED})


def decide_note(
    session: Session,
    note_id: UUID,
    *,
    reviewer: str,
    decisions: list[FlagDecision],
    escalate: bool = False,
    comment: str | None = None,
) -> list[ReviewDecisionRecord]:
    """Decide every pending flag of one note in one transaction, optionally escalating.

    All or nothing: the decisions must cover exactly the note's pending flags, so a note
    never leaves review half-decided, and any invalid edit rolls the whole set back. Each
    flag still goes through `review_flag` (row lock, diff, audit event). Adds rows to the
    session; the caller commits.
    """
    note = session.get(CareNoteRecord, note_id, with_for_update=True)
    if note is None:
        raise NoteNotFoundError(str(note_id))
    ids = [d.flag_id for d in decisions]
    if len(ids) != len(set(ids)):
        raise NoteDecisionError("each flag may be decided once")
    pending = {f.id for f in note.flags if f.review_status is ReviewStatus.PENDING}
    if set(ids) != pending:
        raise NoteDecisionError("decisions must cover exactly the note's pending flags")
    if not note.review_required:
        raise NoteDecisionError("this note is not waiting for review")

    records = [
        review_flag(session, d.flag_id, reviewer=reviewer, action=d.action, edit=d.edit,
                    comment=comment)
        for d in decisions
    ]  # fmt: skip
    if not decisions:  # e.g. the LLM failed and the rules found nothing: acknowledge it
        note.review_required = False
        record(session, EventType.REVIEW_DECISION, actor=f"user:{reviewer}", note_id=note.id,
               output={"action": "acknowledge", "flags": 0, "has_comment": comment is not None,
                       "note_review_required": False})  # fmt: skip

    if escalate:
        session.flush()
        high = [f for f in note.flags if f.severity is Severity.HIGH and f.review_status in _KEPT]
        if not high:
            raise NoteDecisionError("only a note with a kept high-severity flag can be escalated")
        note.escalated_at = datetime.now(UTC)
        note.escalated_by = reviewer
        record(
            session,
            EventType.REVIEW_ESCALATED,
            actor=f"user:{reviewer}",
            note_id=note.id,
            output={
                "to": "care manager",
                "flags": [
                    {"category": f.category.value, "severity": f.severity.value} for f in high
                ],
            },
        )
    return records
