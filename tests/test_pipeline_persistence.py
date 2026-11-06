"""End-to-end pipeline persistence with a fake LLM against the real (test) Postgres."""

import json
from datetime import datetime

import httpx
import pytest
from sqlalchemy import inspect, select

from app.audit.log import input_hash
from app.audit.models import AuditEvent, EventType
from app.nlp.models import (
    CareNoteRecord,
    ExtractionSource,
    ExtractionStatus,
    ReviewStatus,
    RiskFlagRecord,
)
from app.nlp.pipeline import process_note
from app.nlp.prompts import load_prompt
from app.nlp.schemas import CareNote, RiskCategory
from tests.fakes import FakeClient

# All identifiers obviously synthetic (ZZ postcode area, Ofcom drama number).
NOTE = CareNote(
    note_id="T-0001",
    client_ref="CL-0099",
    carer_ref="CR-0099",
    visit_time=datetime(2026, 1, 5, 9, 0),
    text=(
        "Visited Mrs Sampleton at 14 Fictional Avenue, ZZ3 4AB. Daughter rang on 07700 900123. "
        "Found on the floor by the bed. Refused her tablets. Skin checked, no redness."
    ),
)
PII = ["Sampleton", "Fictional Avenue", "ZZ3 4AB", "07700 900123"]
LLM_REPLY = json.dumps(
    {
        "risk_flags": [
            {
                "category": "falls",
                "evidence": "Found on the floor by the bed",
                "severity": "high",
                "confidence": 0.9,
            }
        ],
        "medication_status": "refused",
        "follow_up_required": True,
        "summary": "Client found on the floor; medication refused.",
    }
)


@pytest.fixture
def prompt():
    return load_prompt("extraction", "v2")


def events(session, note_id) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.note_id == note_id).order_by(AuditEvent.id)
    return list(session.scalars(stmt))


def test_success_persists_note_extractions_flags_and_audit_trail(db_session, prompt) -> None:
    rec = process_note(db_session, NOTE, FakeClient([LLM_REPLY]), prompt)
    db_session.commit()

    assert rec.external_id == "T-0001"
    assert "Sampleton" in rec.raw_text  # kept for the reviewer
    assert "Sampleton" not in rec.redacted_text
    assert {(e.source, e.status) for e in rec.extractions} == {
        (ExtractionSource.LLM, ExtractionStatus.OK),
        (ExtractionSource.BASELINE, ExtractionStatus.OK),
    }

    flags = {(f.source, f.category): f for f in rec.flags}
    falls = flags[(ExtractionSource.LLM, RiskCategory.FALLS)]
    assert falls.review_status is ReviewStatus.PENDING  # high severity
    assert rec.redacted_text[falls.span_start : falls.span_end] == falls.evidence
    # The LLM missed the refused medication; the rules found it, so it's surfaced too.
    meds = flags[(ExtractionSource.BASELINE, RiskCategory.MEDICATION)]
    assert "baseline_only" in meds.review_reasons
    assert rec.review_required is True

    trail = events(db_session, rec.id)
    assert [e.event_type for e in trail] == [
        EventType.NOTE_INGESTED,
        EventType.PII_REDACTED,
        EventType.EXTRACTION_COMPLETED,
        EventType.BASELINE_COMPLETED,
        EventType.FLAGS_ROUTED,
    ]
    llm_event = trail[2]
    assert (llm_event.model_name, llm_event.model_version) == ("fake-model:1b", "sha256-fake")
    assert llm_event.prompt_version == "extraction/v2"
    assert llm_event.prompt_sha256 == prompt.sha256
    assert trail[0].input_hash == input_hash(NOTE.text)  # what arrived
    assert llm_event.input_hash == input_hash(rec.redacted_text)  # what the model saw
    assert trail[1].output == {
        "entities": {"PERSON": 1, "UK_STREET_ADDRESS": 1, "UK_POSTCODE": 1, "PHONE_NUMBER": 1}
    }


def test_audit_trail_contains_no_raw_text_or_identifiers(db_session, prompt) -> None:
    rec = process_note(db_session, NOTE, FakeClient([LLM_REPLY]), prompt)
    db_session.flush()
    dumped = json.dumps(
        [
            {c.key: getattr(e, c.key) for c in inspect(e).mapper.column_attrs}
            for e in events(db_session, rec.id)
        ],
        default=str,
    )
    assert NOTE.text not in dumped
    for value in PII:
        assert value not in dumped


def test_llm_unavailable_still_saves_note_with_baseline_flags(db_session, prompt) -> None:
    down = FakeClient([httpx.ConnectError("connection refused")])
    rec = process_note(db_session, NOTE, down, prompt)
    db_session.flush()

    llm = next(e for e in rec.extractions if e.source is ExtractionSource.LLM)
    assert llm.status is ExtractionStatus.FAILED
    assert llm.errors[0].startswith("llm_unavailable")
    assert rec.review_required is True
    assert {f.source for f in rec.flags} == {ExtractionSource.BASELINE}
    assert all(f.review_status is ReviewStatus.PENDING for f in rec.flags)
    types = [e.event_type for e in events(db_session, rec.id)]
    assert EventType.EXTRACTION_FAILED in types
    routed = events(db_session, rec.id)[-1].output
    assert routed["note_reasons"] == ["extraction_failed"]


def test_rollback_leaves_no_partial_state(db_session, prompt) -> None:
    """Note, flags and audit events form one unit: rolled back together."""
    with db_session.begin_nested():
        rec = process_note(db_session, NOTE, FakeClient([LLM_REPLY]), prompt)
        note_id = rec.id
        db_session.flush()
        db_session.rollback()
    assert db_session.get(CareNoteRecord, note_id) is None
    assert events(db_session, note_id) == []
    assert db_session.scalars(select(RiskFlagRecord)).all() == []
