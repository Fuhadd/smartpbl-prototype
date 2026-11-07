"""API request/response models. Separate from the ORM models, so the API contract is
explicit and columns (e.g. `raw_text`) are only exposed by a deliberate change here."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.audit.models import EventType, SubjectType
from app.nlp.ground import GroundingStatus
from app.nlp.models import ExtractionSource, ExtractionStatus, ReviewAction, ReviewStatus
from app.nlp.review import FlagDecision, FlagEdit
from app.nlp.schemas import RiskCategory, Severity


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FlagOut(_Out):
    id: UUID
    source: ExtractionSource
    category: RiskCategory
    severity: Severity
    evidence: str
    confidence: float
    grounding_status: GroundingStatus
    grounding_score: float
    span_start: int | None  # offsets into the note's redacted_text, for highlighting
    span_end: int | None
    review_reasons: list[str]
    review_status: ReviewStatus


class ExtractionOut(_Out):
    source: ExtractionSource
    status: ExtractionStatus
    model_name: str | None
    model_version: str | None
    prompt_version: str | None
    attempts: int
    latency_ms: float | None
    errors: list[str]
    extraction: dict[str, Any] | None


class NoteOut(_Out):
    """Redacted text only: raw text is withheld until role-based access exists (Tier 4)."""

    id: UUID
    external_id: str | None
    client_ref: str
    carer_ref: str
    visit_time: datetime
    redacted_text: str
    review_required: bool
    created_at: datetime
    escalated_at: datetime | None
    escalated_by: str | None
    flags: list[FlagOut]
    extractions: list[ExtractionOut]


class QueueItem(BaseModel):
    note_id: UUID
    external_id: str | None
    client_ref: str
    carer_ref: str
    visit_time: datetime
    created_at: datetime
    redacted_text: str
    extraction_failed: bool
    priority: Severity  # highest pending severity; a failed extraction counts as medium
    pending_flags: list[FlagOut]


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    edit: FlagEdit | None = None
    comment: str | None = Field(default=None, max_length=1000)


class NoteReviewIn(BaseModel):
    """Decide all of a note's pending flags at once (Step 5.2 review screen)."""

    model_config = ConfigDict(extra="forbid")

    decisions: list[FlagDecision] = Field(max_length=50)
    escalate: bool = False
    comment: str | None = Field(default=None, max_length=1000)


class NoteReviewOut(BaseModel):
    note: "NoteOut"
    decision_ids: list[UUID]
    escalated: bool


class ReviewOut(BaseModel):
    decision_id: UUID
    flag: FlagOut
    diff: dict[str, Any]
    note_review_required: bool


class AuditEventOut(_Out):
    id: int
    occurred_at: datetime
    event_type: EventType
    actor: str
    model_name: str | None
    model_version: str | None
    prompt_version: str | None
    prompt_sha256: str | None
    input_hash: str | None
    hash_alg: str | None
    output: dict[str, Any] | None
    subject_type: SubjectType | None
    subject_id: str | None
    request_id: UUID | None
