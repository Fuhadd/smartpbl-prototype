"""End-to-end note processing: redact -> LLM extract -> rules baseline -> ground/route -> persist.

All model work happens before any database write, so a 5-9 s LLM call never holds a
transaction open. Persistence then adds the note, extractions, flags and audit events
to the caller's session in one unit; the caller commits. If the LLM is down or its
output is invalid, the note is still saved, with baseline flags, and queued for review.
"""

from collections import Counter
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.audit.log import record
from app.audit.models import EventType
from app.nlp import baseline
from app.nlp.extract import ExtractionFailedError, ExtractionResult, extract
from app.nlp.llm import ChatClient
from app.nlp.models import (
    CareNoteRecord,
    ExtractionRecord,
    ExtractionSource,
    ExtractionStatus,
    ReviewStatus,
    RiskFlagRecord,
)
from app.nlp.prompts import PromptTemplate
from app.nlp.redact import RedactedText, redact
from app.nlp.route import NoteDecision, decide
from app.nlp.schemas import CareNote, Extraction

PIPELINE_ACTOR = "system:pipeline"


@dataclass(frozen=True)
class _Computed:
    redacted: RedactedText
    llm: ExtractionResult | None
    llm_errors: tuple[str, ...]
    rules: Extraction
    decision: NoteDecision


def _compute(note: CareNote, client: ChatClient, prompt: PromptTemplate) -> _Computed:
    redacted = redact(note.text)
    llm: ExtractionResult | None = None
    errors: tuple[str, ...] = ()
    try:
        llm = extract(redacted, client, prompt)
    except ExtractionFailedError as e:
        errors = e.errors
    except httpx.HTTPError as e:  # Ollama unreachable or erroring: degrade, don't lose the note
        errors = (f"llm_unavailable: {type(e).__name__}: {e}",)
    rules = baseline.extract(redacted.text)
    decision = decide(llm.extraction if llm else None, redacted.text, rules)
    return _Computed(redacted, llm, errors, rules, decision)


def process_note(
    session: Session, note: CareNote, client: ChatClient, prompt: PromptTemplate
) -> CareNoteRecord:
    c = _compute(note, client, prompt)

    rec = CareNoteRecord(
        external_id=note.note_id,
        client_ref=note.client_ref,
        carer_ref=note.carer_ref,
        visit_time=note.visit_time,
        raw_text=note.text,
        redacted_text=c.redacted.text,
        # A carer's urgent concern always reaches a human, whatever the models found.
        review_required=c.decision.review_required or note.urgent,
        visit_id=note.visit_id,
        urgent=note.urgent,
        tasks_done=note.tasks_done or None,
    )
    session.add(rec)
    session.flush()  # assigns rec.id for the child rows and audit events

    record(
        session,
        EventType.NOTE_INGESTED,
        actor=PIPELINE_ACTOR,
        note_id=rec.id,
        input_text=note.text,
        output={"external_id": note.note_id, "visit_id": note.visit_id, "urgent": note.urgent},
    )
    record(
        session,
        EventType.PII_REDACTED,
        actor=PIPELINE_ACTOR,
        note_id=rec.id,
        input_text=note.text,
        output={"entities": dict(Counter(s.entity_type for s in c.redacted.spans))},
    )

    llm_rec = _persist_llm(session, rec, c)
    rules_rec = ExtractionRecord(
        note_id=rec.id,
        source=ExtractionSource.BASELINE,
        status=ExtractionStatus.OK,
        extraction=c.rules.model_dump(mode="json"),
        model_name="rules",
        model_version=baseline.BASELINE_VERSION,
    )
    session.add(rules_rec)
    record(
        session,
        EventType.BASELINE_COMPLETED,
        actor=PIPELINE_ACTOR,
        note_id=rec.id,
        input_text=c.redacted.text,
        output=rules_rec.extraction,
        model_name="rules",
        model_version=baseline.BASELINE_VERSION,
    )
    session.flush()

    flags = []
    for d in c.decision.flags:
        flag = RiskFlagRecord(
            note_id=rec.id,
            extraction_id=(llm_rec.id if d.source == "llm" and llm_rec else rules_rec.id),
            source=ExtractionSource(d.source),
            category=d.flag.category,
            severity=d.flag.severity,
            evidence=d.flag.evidence,
            confidence=d.flag.confidence,
            grounding_status=d.grounding.status,
            grounding_score=d.grounding.score,
            span_start=d.grounding.start,
            span_end=d.grounding.end,
            review_reasons=[r.value for r in d.reasons],
            review_status=ReviewStatus.PENDING if d.needs_review else ReviewStatus.AUTO_ACCEPTED,
        )
        session.add(flag)
        flags.append(flag)
    session.flush()

    record(
        session,
        EventType.FLAGS_ROUTED,
        actor=PIPELINE_ACTOR,
        note_id=rec.id,
        output={
            "review_required": rec.review_required,
            "urgent": note.urgent,
            "note_reasons": [r.value for r in c.decision.note_reasons],
            "flags": [
                {
                    "flag_id": str(f.id),
                    "source": f.source.value,
                    "category": f.category.value,
                    "severity": f.severity.value,
                    "grounding": f.grounding_status.value,
                    "reasons": f.review_reasons,
                    "review_status": f.review_status.value,
                }
                for f in flags
            ],
        },
    )
    return rec


def _persist_llm(session: Session, rec: CareNoteRecord, c: _Computed) -> ExtractionRecord:
    r = c.llm
    llm_rec = ExtractionRecord(
        note_id=rec.id,
        source=ExtractionSource.LLM,
        status=ExtractionStatus.OK if r else ExtractionStatus.FAILED,
        extraction=r.extraction.model_dump(mode="json") if r else None,
        model_name=r.model if r else None,
        model_version=r.model_digest if r else None,
        prompt_version=r.prompt_version if r else None,
        prompt_sha256=r.prompt_sha256 if r else None,
        attempts=r.attempts if r else len(c.llm_errors),
        latency_ms=r.latency_ms if r else None,
        errors=list(r.errors if r else c.llm_errors),
        overrides=list(r.overrides) if r else [],
    )
    session.add(llm_rec)
    record(
        session,
        EventType.EXTRACTION_COMPLETED if r else EventType.EXTRACTION_FAILED,
        actor=PIPELINE_ACTOR,
        note_id=rec.id,
        input_text=c.redacted.text,  # what the model actually received
        output={
            "extraction": llm_rec.extraction,
            "attempts": llm_rec.attempts,
            "errors": llm_rec.errors,
            "overrides": llm_rec.overrides,
        },
        model_name=llm_rec.model_name,
        model_version=llm_rec.model_version,
        prompt_version=llm_rec.prompt_version,
        prompt_sha256=llm_rec.prompt_sha256,
    )
    session.flush()
    return llm_rec
