"""GET /review/queue and POST /review/{flag_id}."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require
from app.api.schemas import (
    FlagOut,
    NoteOut,
    NoteReviewIn,
    NoteReviewOut,
    QueueItem,
    ReviewIn,
    ReviewOut,
)
from app.audit.log import record
from app.audit.models import EventType
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.db import get_session
from app.nlp.models import (
    CareNoteRecord,
    ExtractionSource,
    ExtractionStatus,
    ReviewStatus,
    RiskFlagRecord,
)
from app.nlp.review import (
    AlreadyReviewedError,
    FlagNotFoundError,
    InvalidEditError,
    NoteDecisionError,
    NoteNotFoundError,
    decide_note,
    review_flag,
)
from app.nlp.schemas import Severity

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(get_current_user)])
SessionDep = Annotated[Session, Depends(get_session)]
_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _queue_item(note: CareNoteRecord) -> QueueItem:
    pending = [f for f in note.flags if f.review_status is ReviewStatus.PENDING]
    failed = any(
        e.source is ExtractionSource.LLM and e.status is ExtractionStatus.FAILED
        for e in note.extractions
    )
    severities = [f.severity for f in pending] + ([Severity.MEDIUM] if failed else [])
    priority = max(severities, key=_RANK.__getitem__, default=Severity.LOW)
    pending.sort(key=lambda f: -_RANK[f.severity])
    return QueueItem(
        note_id=note.id,
        external_id=note.external_id,
        client_ref=note.client_ref,
        carer_ref=note.carer_ref,
        visit_time=note.visit_time,
        created_at=note.created_at,
        redacted_text=note.redacted_text,
        extraction_failed=failed,
        priority=priority,
        pending_flags=[FlagOut.model_validate(f) for f in pending],
    )


def queue_items(session: Session) -> list[QueueItem]:
    """Every note needing a human decision, in queue order (also used by the overview).

    Sorted in Python over all notes needing review: fine at prototype volumes; at scale,
    store a priority column and sort and page in SQL.
    """
    notes = session.scalars(
        select(CareNoteRecord)
        .where(CareNoteRecord.review_required.is_(True))
        .options(selectinload(CareNoteRecord.flags), selectinload(CareNoteRecord.extractions))
    ).all()
    return sorted(map(_queue_item, notes), key=lambda q: (-_RANK[q.priority], q.created_at))


@router.get("/queue")
def review_queue(
    viewer: Annotated[User, Depends(require(Permission.REVIEW_QUEUE_READ))],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[QueueItem]:
    """Notes needing a human decision: highest pending severity first, then oldest first."""
    page = queue_items(session)[:limit]
    # The queue discloses redacted note text: record exactly which notes were shown.
    record(session, EventType.REVIEW_QUEUE_VIEWED, actor=f"user:{viewer.username}",
           output={"note_ids": [str(q.note_id) for q in page], "limit": limit})  # fmt: skip
    session.commit()
    return page


@router.post("/{flag_id}")
def review(
    reviewer: Annotated[User, Depends(require(Permission.REVIEW_DECIDE))],
    flag_id: UUID,
    body: ReviewIn,
    session: SessionDep,
) -> ReviewOut:
    try:
        decision = review_flag(
            session,
            flag_id,
            reviewer=reviewer.username,
            action=body.action,
            edit=body.edit,
            comment=body.comment,
        )
    except FlagNotFoundError as e:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found") from e
    except AlreadyReviewedError as e:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except InvalidEditError as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    flag = session.get_one(RiskFlagRecord, decision.flag_id)
    session.commit()
    return ReviewOut(
        decision_id=decision.id,
        flag=FlagOut.model_validate(flag),
        diff=decision.diff,
        note_review_required=flag.note.review_required,
    )


@router.post("/notes/{note_id}")
def review_note(
    reviewer: Annotated[User, Depends(require(Permission.REVIEW_DECIDE))],
    note_id: UUID,
    body: NoteReviewIn,
    session: SessionDep,
) -> NoteReviewOut:
    """Approve, edit or reject every pending flag of a note, atomically, and optionally
    escalate it to a care manager. One `review_decision` audit event per flag, plus a
    `review_escalated` event."""
    try:
        decisions = decide_note(
            session,
            note_id,
            reviewer=reviewer.username,
            decisions=body.decisions,
            escalate=body.escalate,
            comment=body.comment,
        )
    except NoteNotFoundError as e:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "note not found") from e
    except (AlreadyReviewedError, NoteDecisionError) as e:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except InvalidEditError as e:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    note = session.get_one(CareNoteRecord, note_id)
    session.refresh(note)
    return NoteReviewOut(
        note=NoteOut.model_validate(note),
        decision_ids=[d.id for d in decisions],
        escalated=body.escalate,
    )
