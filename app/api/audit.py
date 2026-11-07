"""The audit log API.

- GET /audit: the grouped timeline the audit screen shows (app/audit/timeline.py).
- GET /audit/summary: today's counts for the tiles above it.
- GET /audit/export: the same timeline as CSV.
- GET /audit/{note_id}: every raw row about one note, including who accessed it.

All are reads of the log, so each is itself recorded by the audit middleware.
"""

import csv
import io
from datetime import datetime, time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require
from app.api.schemas import AuditEventOut
from app.audit.models import AuditEvent, EventType, SubjectType
from app.audit.timeline import (
    DISPLAY_TZ,
    FILTER_KINDS,
    MAX_PAGE,
    AuditPage,
    EntryFilter,
    actor_label,
    timeline_page,
)
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.db import get_session
from app.nlp.models import ReviewStatus, RiskFlagRecord

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(get_current_user)])
ReaderDep = Annotated[User, Depends(require(Permission.AUDIT_READ))]
SessionDep = Annotated[Session, Depends(get_session)]
SearchQ = Annotated[str | None, Query(max_length=100)]
EXPORT_MAX = 5000  # entries per CSV: a bounded response (OWASP API4)
# OWASP CSV Injection: formula triggers, control characters and full-width lookalikes.
CSV_FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n", "\uff1d", "\uff0b", "\uff0d", "\uff20")


class AuditSummary(BaseModel):
    day: str  # ISO date in the provider's time zone (Europe/London)
    entries_today: int  # raw rows appended today, of every type
    high_flags_today: int  # flags routed to review as high severity today
    high_flags_reviewed: int  # ...of which a person has decided
    human_overrides: int  # reviewer edits or rejections today
    access_denied: int  # requests refused with 403 today


@router.get("")
def audit_timeline(
    _: ReaderDep,
    session: SessionDep,
    kind: EntryFilter = EntryFilter.ALL,
    q: SearchQ = None,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
) -> AuditPage:
    """Newest first, one entry per meaningful event, each listing the raw rows behind it.
    Page with `before=<next_before>`."""
    return timeline_page(session, kinds=FILTER_KINDS[kind], q=q, before=before, limit=limit)


@router.get("/summary")
def audit_summary(_: ReaderDep, session: SessionDep) -> AuditSummary:
    now = datetime.now(DISPLAY_TZ)
    start = datetime.combine(now.date(), time.min, tzinfo=DISPLAY_TZ)
    today = AuditEvent.occurred_at >= start
    entries = session.scalar(select(func.count()).where(today))
    overrides = session.scalar(
        select(func.count()).where(
            today,
            AuditEvent.event_type == EventType.REVIEW_DECISION,
            AuditEvent.output["action"].as_string().in_(("edit", "reject")),
        )
    )
    denied = session.scalar(
        select(func.count()).where(
            today,
            AuditEvent.event_type == EventType.API_REQUEST,
            AuditEvent.output["status"].as_integer() == 403,
        )
    )
    # Severity at routing time (a reviewer may since have edited it down).
    high = RiskFlagRecord.review_reasons.contains(["high_severity"])
    undecided = (ReviewStatus.PENDING, ReviewStatus.AUTO_ACCEPTED)
    total, reviewed = session.execute(
        select(
            func.count(), func.count().filter(RiskFlagRecord.review_status.not_in(undecided))
        ).where(RiskFlagRecord.created_at >= start, high)
    ).one()
    return AuditSummary(
        day=now.date().isoformat(),
        entries_today=entries or 0,
        high_flags_today=total,
        high_flags_reviewed=reviewed,
        human_overrides=overrides or 0,
        access_denied=denied or 0,
    )


def _cell(value: object) -> str:
    """Neutralise spreadsheet formulas (CSV injection): a cell starting with = + - @ would
    run as a formula when the export is opened in Excel. Actor names and search-derived
    fields are user-influenced, so prefix such cells with an apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(CSV_FORMULA_START) else text


@router.get("/export", response_class=Response)
def audit_export(
    _: ReaderDep,
    session: SessionDep,
    kind: EntryFilter = EntryFilter.ALL,
    q: SearchQ = None,
) -> Response:
    """The filtered timeline as CSV (newest first, at most 5000 entries)."""
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(["time_utc", "event", "actor", "subject", "version", "result", "event_ids"])
    before, written = None, 0
    while written < EXPORT_MAX:
        page = timeline_page(
            session,
            kinds=FILTER_KINDS[kind],
            q=q,
            before=before,
            limit=min(MAX_PAGE, EXPORT_MAX - written),
        )
        for e in page.entries:
            out.writerow(
                [
                    _cell(v)
                    for v in (
                        e.occurred_at.isoformat(),
                        e.kind.value,
                        actor_label(e.actor),
                        e.subject,
                        e.version,
                        e.result,
                        " ".join(map(str, e.event_ids)),
                    )
                ]
            )
        written += len(page.entries)
        if page.next_before is None:
            break
        before = page.next_before
    stamp = datetime.now(DISPLAY_TZ).strftime("%Y%m%d-%H%M")
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="smartpbl-audit-{stamp}.csv"'},
    )


@router.get("/{note_id}")
def audit_trail(_: ReaderDep, note_id: UUID, session: SessionDep) -> list[AuditEventOut]:
    """Everything the log knows about one note, in insertion order (by id, not timestamp:
    events in one transaction share now()):

    - the note's own events (ingestion, extraction, routing, review decisions);
    - the API requests that caused them, joined by request id (so: who submitted it);
    - every direct access to the note (`/notes/{id}`, `/audit/{id}`), by subject;
    - review-queue views that displayed it.

    Works even if the note itself has since been deleted (no foreign key, by design).
    """
    nid = str(note_id)
    names_note = or_(
        AuditEvent.note_id == note_id,
        and_(AuditEvent.subject_type == SubjectType.CARE_NOTE, AuditEvent.subject_id == nid),
        and_(
            AuditEvent.event_type == EventType.REVIEW_QUEUE_VIEWED,
            AuditEvent.output.contains({"note_ids": [nid]}),
        ),
    )
    request_ids = select(AuditEvent.request_id).where(
        names_note, AuditEvent.request_id.is_not(None)
    )
    caused_by = and_(
        AuditEvent.event_type == EventType.API_REQUEST, AuditEvent.request_id.in_(request_ids)
    )
    events = session.scalars(
        select(AuditEvent).where(or_(names_note, caused_by)).order_by(AuditEvent.id)
    ).all()
    if not events:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no audit events for this note")
    return [AuditEventOut.model_validate(e) for e in events]
