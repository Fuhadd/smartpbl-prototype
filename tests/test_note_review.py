"""POST /review/notes/{id}: decide a whole note atomically, optionally escalating."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_llm_client
from app.audit.models import AuditEvent, EventType
from app.auth.models import Role
from app.core.db import get_session
from app.main import app
from app.nlp.models import ReviewDecisionRecord
from tests.fakes import FakeClient
from tests.test_api import FALL_REPLY, FALL_TEXT, flag, post_note


@pytest.fixture
def llm() -> FakeClient:
    return FakeClient([])


@pytest.fixture
def api(db_session, llm, auth_headers) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_llm_client] = lambda: llm
    with TestClient(app, headers=auth_headers(Role.COORDINATOR)) as client:
        yield client
    app.dependency_overrides.clear()


def pending(note: dict) -> list[dict]:
    return [f for f in note["flags"] if f["review_status"] == "pending"]


def decide(api, note: dict, **body):
    return api.post(f"/review/notes/{note['id']}", json=body)


def test_approving_every_pending_flag_settles_the_note(api, llm, db_session) -> None:
    note = post_note(api, llm, "NR-1", FALL_TEXT, FALL_REPLY)
    flags = pending(note)
    assert flags, "fixture note must need review"
    r = decide(api, note, decisions=[{"flag_id": f["id"], "action": "approve"} for f in flags])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["note"]["review_required"] is False and out["escalated"] is False
    assert len(out["decision_ids"]) == len(flags)
    assert note["id"] not in [q["note_id"] for q in api.get("/review/queue").json()]
    assert db_session.query(ReviewDecisionRecord).count() == len(flags)


def test_mixed_decisions_apply_per_flag(api, llm) -> None:
    note = post_note(api, llm, "NR-2", FALL_TEXT, FALL_REPLY)
    falls = flag(note, "falls")
    others = [f for f in pending(note) if f["id"] != falls["id"]]
    decisions = [{"flag_id": falls["id"], "action": "edit", "edit": {"severity": "medium"}}]
    decisions += [{"flag_id": f["id"], "action": "reject"} for f in others]
    out = decide(api, note, decisions=decisions).json()
    by_id = {f["id"]: f for f in out["note"]["flags"]}
    assert by_id[falls["id"]]["review_status"] == "edited"
    assert by_id[falls["id"]]["severity"] == "medium"
    assert all(by_id[f["id"]]["review_status"] == "rejected" for f in others)


def test_escalation_is_recorded_on_the_note_and_in_the_audit_log(api, llm, db_session) -> None:
    note = post_note(api, llm, "NR-3", FALL_TEXT, FALL_REPLY)
    approve_all = [{"flag_id": f["id"], "action": "approve"} for f in pending(note)]
    out = decide(api, note, decisions=approve_all, escalate=True).json()
    assert out["escalated"] is True
    assert out["note"]["escalated_by"] == "coord.alpha" and out["note"]["escalated_at"]
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == EventType.REVIEW_ESCALATED)
    )
    assert event.actor == "user:coord.alpha"
    assert {"category": "falls", "severity": "high"} in event.output["flags"]


def test_escalation_needs_a_kept_high_flag_and_nothing_is_applied_otherwise(api, llm) -> None:
    note = post_note(api, llm, "NR-4", FALL_TEXT, FALL_REPLY)
    reject_all = [{"flag_id": f["id"], "action": "reject"} for f in pending(note)]
    r = decide(api, note, decisions=reject_all, escalate=True)
    assert r.status_code == 409 and "high-severity" in r.json()["detail"]
    after = api.get(f"/notes/{note['id']}").json()
    assert pending(after) == pending(note)  # all-or-nothing: no flag was rejected


@pytest.mark.parametrize("variant", ["missing", "duplicate", "foreign"])
def test_decisions_must_cover_exactly_the_pending_flags(api, llm, variant) -> None:
    note = post_note(api, llm, f"NR-5-{variant}", FALL_TEXT, FALL_REPLY)
    flags = pending(note)
    ids = {"missing": [f["id"] for f in flags[:-1]],
           "duplicate": [f["id"] for f in flags] + [flags[0]["id"]],
           "foreign": [f["id"] for f in flags] + [str(uuid4())]}[variant]  # fmt: skip
    r = decide(api, note, decisions=[{"flag_id": i, "action": "approve"} for i in ids])
    assert r.status_code == 409


def test_one_invalid_edit_rolls_back_the_whole_note(api, llm) -> None:
    note = post_note(api, llm, "NR-6", FALL_TEXT, FALL_REPLY)
    flags = pending(note)
    decisions = [{"flag_id": f["id"], "action": "approve"} for f in flags[:-1]]
    decisions.append({"flag_id": flags[-1]["id"], "action": "edit",
                      "edit": {"evidence": "words that are not in the note at all"}})  # fmt: skip
    r = decide(api, note, decisions=decisions)
    assert r.status_code == 422
    assert pending(api.get(f"/notes/{note['id']}").json()) == flags


def test_a_settled_note_cannot_be_decided_again(api, llm) -> None:
    note = post_note(api, llm, "NR-7", FALL_TEXT, FALL_REPLY)
    approve_all = [{"flag_id": f["id"], "action": "approve"} for f in pending(note)]
    assert decide(api, note, decisions=approve_all).status_code == 200
    assert decide(api, note, decisions=[]).status_code == 409


def test_unknown_note_is_404(api) -> None:
    assert api.post(f"/review/notes/{uuid4()}", json={"decisions": []}).status_code == 404


def test_queue_items_name_the_carer(api, llm) -> None:
    post_note(api, llm, "NR-8", FALL_TEXT, FALL_REPLY)
    [item] = api.get("/review/queue").json()
    assert item["carer_ref"] == "CR-0099"
