"""Persistence for notes, extractions and flags (operational state, unlike the audit log).

`risk_flags.review_status` is mutable workflow state. Every change to it is also
written to the append-only audit log (Step 1.8), which is the history.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin
from app.nlp.ground import GroundingStatus
from app.nlp.schemas import RiskCategory, Severity


def _enum(e: type[StrEnum], length: int = 30) -> Enum:
    # VARCHAR + CHECK constraint (not a native PG enum): adding a value is a simple migration.
    return Enum(
        e,
        native_enum=False,
        create_constraint=True,  # CHECK constraint: the DB itself rejects unknown values
        length=length,
        values_callable=lambda x: [m.value for m in x],
    )


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
    source: Mapped[ExtractionSource] = mapped_column(_enum(ExtractionSource))
    status: Mapped[ExtractionStatus] = mapped_column(_enum(ExtractionStatus))
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
    source: Mapped[ExtractionSource] = mapped_column(_enum(ExtractionSource))
    category: Mapped[RiskCategory] = mapped_column(_enum(RiskCategory))
    severity: Mapped[Severity] = mapped_column(_enum(Severity))
    evidence: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float]
    grounding_status: Mapped[GroundingStatus] = mapped_column(_enum(GroundingStatus))
    grounding_score: Mapped[float]
    span_start: Mapped[int | None]  # offsets into redacted_text, for highlighting
    span_end: Mapped[int | None]
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    review_status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus), index=True)

    note: Mapped[CareNoteRecord] = relationship(back_populates="flags")
