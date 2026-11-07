"""Append-only audit log.

Rows are inserted, never changed. A Postgres trigger (migration 0001) rejects UPDATE,
DELETE and TRUNCATE. The note itself is never stored here: only a keyed hash of it
(`input_hash`), so the log can outlive the note (retention, erasure) without
carrying personal data.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, string_enum


class EventType(StrEnum):
    NOTE_INGESTED = "note_ingested"
    PII_REDACTED = "pii_redacted"
    EXTRACTION_COMPLETED = "extraction_completed"
    EXTRACTION_FAILED = "extraction_failed"
    BASELINE_COMPLETED = "baseline_completed"
    FLAGS_ROUTED = "flags_routed"
    REVIEW_DECISION = "review_decision"  # Step 1.8
    SCHEDULE_SOLVED = "schedule_solved"  # Step 2.6
    WORKFORCE_RISK_VIEWED = "workforce_risk_viewed"  # Step 3.4: who saw which carers' risk
    WORKFORCE_EXPLANATION_VIEWED = "workforce_explanation_viewed"
    # Step 4.2: one row per routed API call (who, what, outcome), written by middleware.
    API_REQUEST = "api_request"
    REVIEW_QUEUE_VIEWED = "review_queue_viewed"  # which notes' text a reviewer was shown
    REVIEW_ESCALATED = "review_escalated"  # Step 5.2: sent to a care manager for sign-off
    REFRESH_TOKEN_REUSE_DETECTED = "refresh_token_reuse_detected"  # noqa: S105  (event name)  # likely token theft


class SubjectType(StrEnum):
    """What an audit row is about. `subject_id` is the id in that type's namespace."""

    CARE_NOTE = "care_note"
    RISK_FLAG = "risk_flag"
    SCHEDULE_RUN = "schedule_run"
    CARER = "carer"
    USER = "user"


class AuditEvent(Base):
    __tablename__ = "audit_events"

    # bigserial gives a total order, even for events in one transaction (same now()).
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(
            EventType,
            native_enum=False,
            create_constraint=True,
            length=40,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(String(100), nullable=False)  # "system:pipeline", user id
    # Deliberately not a foreign key: audit rows must survive deletion of the note.
    note_id: Mapped[UUID | None] = mapped_column(index=True)
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))  # weights digest
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    hash_alg: Mapped[str | None] = mapped_column(String(20))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Step 4.2. Generic subject (note_id stays for note events, so older rows still match).
    subject_type: Mapped[SubjectType | None] = mapped_column(string_enum(SubjectType))
    subject_id: Mapped[str | None] = mapped_column(String(100))
    # Correlates every event caused by one HTTP request (also sent as X-Request-ID).
    request_id: Mapped[UUID | None] = mapped_column(index=True)

    __table_args__ = (Index("ix_audit_events_subject", "subject_type", "subject_id"),)
