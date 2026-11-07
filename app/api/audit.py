"""GET /audit/{note_id}: the append-only event trail for one note, including who\naccessed it."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require
from app.api.schemas import AuditEventOut
from app.audit.models import AuditEvent, EventType, SubjectType
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.db import get_session

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(get_current_user)])


@router.get("/{note_id}")
def audit_trail(
    _: Annotated[User, Depends(require(Permission.AUDIT_READ))],
    note_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[AuditEventOut]:
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
