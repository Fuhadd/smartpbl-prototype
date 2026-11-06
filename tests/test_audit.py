import hashlib

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.audit.log import HASH_ALG, input_hash, record
from app.audit.models import AuditEvent, EventType
from app.core.config import Settings


def test_input_hash_is_keyed_and_deterministic(monkeypatch) -> None:
    note = "AM call. All well."
    h = input_hash(note)
    assert h == input_hash(note)
    assert len(h) == 64
    # Not a plain SHA-256: a dictionary attack (hash guesses, compare) would not match.
    assert h != hashlib.sha256(note.encode()).hexdigest()
    monkeypatch.setattr(
        "app.audit.log.get_settings", lambda: Settings(audit_hash_key="another-key")
    )
    assert input_hash(note) != h  # depends on the secret key


def test_record_persists_event_with_hash_not_text(db_session) -> None:
    record(db_session, EventType.NOTE_INGESTED, actor="tester", input_text="Mrs Sampleton fell")
    db_session.flush()
    event = db_session.scalars(select(AuditEvent)).one()
    assert event.occurred_at is not None
    assert event.hash_alg == HASH_ALG
    assert event.input_hash == input_hash("Mrs Sampleton fell")
    assert "Sampleton" not in repr(event.__dict__)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET actor = 'tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_audit_log_is_append_only(db_session, statement: str) -> None:
    record(db_session, EventType.NOTE_INGESTED, actor="tester")
    db_session.flush()
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(text(statement))
    assert db_session.scalars(select(AuditEvent.actor)).all() == ["tester"]


def test_orm_update_is_also_rejected(db_session) -> None:
    event = record(db_session, EventType.NOTE_INGESTED, actor="tester")
    db_session.flush()
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        event.actor = "tampered"
        db_session.flush()


def test_unknown_event_type_rejected_by_database(db_session) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_audit_events_eventtype"),
        db_session.begin_nested(),
    ):
        db_session.execute(
            text("INSERT INTO audit_events (event_type, actor) VALUES ('made_up', 'tester')")
        )
