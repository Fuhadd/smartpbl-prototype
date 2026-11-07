"""GET /audit/{note_id}: the append-only event trail for one note."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require
from app.api.schemas import AuditEventOut
from app.audit.models import AuditEvent
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
    """Ordered by id (insertion order), not timestamp: events in one transaction share now().
    Works even if the note itself has since been deleted (no foreign key, by design)."""
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.note_id == note_id).order_by(AuditEvent.id)
    ).all()
    if not events:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no audit events for this note")
    return [AuditEventOut.model_validate(e) for e in events]
