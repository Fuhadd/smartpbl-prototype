"""Persistence for notes, extractions and flags (operational state, unlike the audit log).

`risk_flags` holds the current (possibly reviewer-edited) flag; mutable workflow state.
`review_decisions` records each human decision with a before/after diff, queryable for
metrics and future training labels. Every decision is also written to the append-only
audit log, which is the tamper-resistant history.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin, string_enum
from app.nlp.ground import GroundingStatus
from app.nlp.schemas import RiskCategory, Severity


class ExtractionSource(StrEnum):
    LLM = "llm"
    BASELINE = "baseline"


class ExtractionStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    AUTO_ACCEPTED = "auto_accepted"
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ReviewAction(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class CareNoteRecord(CreatedAtMixin, Base):
    __tablename__ = "care_notes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    external_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    client_ref: Mapped[str] = mapped_column(String(50), index=True)
    carer_ref: Mapped[str] = mapped_column(String(50), index=True)
    visit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Raw text is personal health data: kept for the reviewer, never sent to the LLM or the
    # audit log. Prototype limitation: no column-level encryption (see BACKLOG).
    raw_text: Mapped[str] = mapped_column(Text)
    redacted_text: Mapped[str] = mapped_column(Text)
    review_required: Mapped[bool]

    extractions: Mapped[list["ExtractionRecord"]] = relationship(back_populates="note")
    flags: Mapped[list["RiskFlagRecord"]] = relationship(back_populates="note")


class ExtractionRecord(CreatedAtMixin, Base):
    __tablename__ = "extractions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    note_id: Mapped[UUID] = mapped_column(ForeignKey("care_notes.id"), index=True)
    source: Mapped[ExtractionSource] = mapped_column(string_enum(ExtractionSource))
    status: Mapped[ExtractionStatus] = mapped_column(string_enum(ExtractionStatus))
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model_name: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    overrides: Mapped[list[str]] = mapped_column(JSONB, default=list)

    note: Mapped[CareNoteRecord] = relationship(back_populates="extractions")


class RiskFlagRecord(CreatedAtMixin, Base):
    __tablename__ = "risk_flags"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    note_id: Mapped[UUID] = mapped_column(ForeignKey("care_notes.id"), index=True)
    extraction_id: Mapped[UUID] = mapped_column(ForeignKey("extractions.id"))
    source: Mapped[ExtractionSource] = mapped_column(string_enum(ExtractionSource))
    category: Mapped[RiskCategory] = mapped_column(string_enum(RiskCategory))
    severity: Mapped[Severity] = mapped_column(string_enum(Severity))
    evidence: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float]
    grounding_status: Mapped[GroundingStatus] = mapped_column(string_enum(GroundingStatus))
    grounding_score: Mapped[float]
    span_start: Mapped[int | None]  # offsets into redacted_text, for highlighting
    span_end: Mapped[int | None]
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    review_status: Mapped[ReviewStatus] = mapped_column(string_enum(ReviewStatus), index=True)

    note: Mapped[CareNoteRecord] = relationship(back_populates="flags")


class ReviewDecisionRecord(CreatedAtMixin, Base):
    __tablename__ = "review_decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    flag_id: Mapped[UUID] = mapped_column(ForeignKey("risk_flags.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(100))
    action: Mapped[ReviewAction] = mapped_column(string_enum(ReviewAction))
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB)  # {field: {"before": x, "after": y}}
    comment: Mapped[str | None] = mapped_column(String(1000))
