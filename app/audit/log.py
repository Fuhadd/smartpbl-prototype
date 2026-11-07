"""Writing audit events and hashing their inputs."""

import hashlib
import hmac
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.audit import context
from app.audit.models import AuditEvent, EventType, SubjectType
from app.core.config import get_settings

HASH_ALG = "hmac-sha256"


def input_hash(text: str) -> str:
    """Keyed SHA-256 (HMAC) of the input text.

    A plain SHA-256 of a short, predictable note ("AM call. All well.") can be reversed
    by hashing candidate texts and comparing (a dictionary attack). With a secret key,
    only the key holder can test a guess. The same text and key always give the same
    hash, so the log can still prove which input produced which output.
    """
    key = get_settings().audit_hash_key.get_secret_value().encode()
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def record(
    session: Session,
    event_type: EventType,
    *,
    actor: str,
    note_id: UUID | None = None,
    input_text: str | None = None,
    output: dict[str, Any] | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    prompt_version: str | None = None,
    prompt_sha256: str | None = None,
    subject: tuple[SubjectType, str] | None = None,
) -> AuditEvent:
    """Add an audit event to the session. It's committed with the caller's transaction,
    so it lands if and only if the action it describes does.

    Every event is stamped with the current request's id (None outside a request), so a
    model decision links back to the authenticated call that caused it. Note events get
    the note as their subject unless another subject is given.
    """
    if subject is None and note_id is not None:
        subject = (SubjectType.CARE_NOTE, str(note_id))
    ctx = context.current()
    event = AuditEvent(
        event_type=event_type,
        actor=actor,
        note_id=note_id,
        input_hash=input_hash(input_text) if input_text is not None else None,
        hash_alg=HASH_ALG if input_text is not None else None,
        output=output,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        subject_type=subject[0] if subject else None,
        subject_id=subject[1] if subject else None,
        request_id=ctx.request_id if ctx else None,
    )
    session.add(event)
    return event
