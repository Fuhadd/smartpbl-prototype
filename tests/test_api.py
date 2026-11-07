"""API integration tests: real routers, real (test) Postgres, LLM replaced by FakeClient."""

import json
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.api.deps import get_llm_client
from app.auth.models import Role
from app.core.db import get_session
from app.main import app
from app.nlp.models import ReviewDecisionRecord
from tests.fakes import FakeClient

# Obviously synthetic: placeholder surname, ZZ postcode area, Ofcom drama number.
FALL_TEXT = (
    "Visited Mrs Sampleton at 14 Fictional Avenue, ZZ3 4AB. Daughter rang on 07700 900123. "
    "Found on the floor by the bed. Refused her tablets."
)
PII = ["Sampleton", "Fictional Avenue", "ZZ3 4AB", "07700 900123"]


def reply(*flags: tuple[str, str, str, float], medication: str = "not_mentioned") -> str:
    return json.dumps(
        {
            "risk_flags": [
                {"category": c, "evidence": e, "severity": s, "confidence": conf}
                for c, e, s, conf in flags
            ],
            "medication_status": medication,
            "follow_up_required": False,  # derived in code anyway
            "summary": "Synthetic summary.",
        }
    )


FALL_REPLY = reply(
    ("falls", "Found on the floor by the bed", "high", 0.9),
    ("medication", "Refused her tablets", "medium", 0.9),
    medication="refused",
)


@pytest.fixture
def llm() -> FakeClient:
    return FakeClient([])


@pytest.fixture
def as_manager(auth_headers) -> dict[str, str]:
    return auth_headers(Role.MANAGER)


@pytest.fixture
def api(db_session, llm, auth_headers) -> Iterator[TestClient]:
    """Authenticated as a coordinator by default; audit reads pass manager headers."""
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_llm_client] = lambda: llm
    with TestClient(app, headers=auth_headers(Role.COORDINATOR)) as client:
        yield client
    app.dependency_overrides.clear()


def post_note(api, llm, note_id: str, text: str, llm_reply: str | Exception) -> dict:
    llm.replies.append(llm_reply)
    body = {
        "note_id": note_id,
        "client_ref": "CL-0099",
        "carer_ref": "CR-0099",
        "visit_time": "2026-01-05T09:00:00Z",
        "text": text,
    }
    r = api.post("/notes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def flag(note: dict, category: str) -> dict:
    return next(f for f in note["flags"] if f["category"] == category)


# --- POST /notes, GET /notes/{id} ---------------------------------------------------------


def test_create_note_processes_and_returns_redacted_view_only(api, llm) -> None:
    note = post_note(api, llm, "API-1", FALL_TEXT, FALL_REPLY)
    assert "raw_text" not in note
    for value in PII:
        assert value not in json.dumps(note)
    assert note["review_required"] is True
    falls = flag(note, "falls")
    assert falls["review_status"] == "pending"
    assert "high_severity" in falls["review_reasons"]
    assert note["redacted_text"][falls["span_start"] : falls["span_end"]] == falls["evidence"]
    assert flag(note, "medication")["review_status"] == "auto_accepted"
    assert {e["source"] for e in note["extractions"]} == {"llm", "baseline"}

    fetched = api.get(f"/notes/{note['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == note["id"]


def test_duplicate_note_is_409_without_calling_llm(api, llm) -> None:
    post_note(api, llm, "API-2", FALL_TEXT, FALL_REPLY)
    llm.replies.append(FALL_REPLY)
    r = api.post(
        "/notes",
        json={
            "note_id": "API-2",
            "client_ref": "CL-0099",
            "carer_ref": "CR-0099",
            "visit_time": "2026-01-05T09:00:00Z",
            "text": FALL_TEXT,
        },
    )
    assert r.status_code == 409
    assert len(llm.calls) == 1  # rejected before the expensive step


def test_invalid_note_is_422(api) -> None:
    r = api.post("/notes", json={"note_id": "API-3", "text": "x", "surprise": 1})
    assert r.status_code == 422


def test_unknown_note_is_404(api) -> None:
    assert api.get(f"/notes/{uuid4()}").status_code == 404


def test_llm_down_still_creates_note_and_queues_it(api, llm) -> None:
    note = post_note(api, llm, "API-4", FALL_TEXT, httpx.ConnectError("refused"))
    llm_ext = next(e for e in note["extractions"] if e["source"] == "llm")
    assert llm_ext["status"] == "failed"
    item = next(q for q in api.get("/review/queue").json() if q["note_id"] == note["id"])
    assert item["extraction_failed"] is True
    assert {f["source"] for f in item["pending_flags"]} == {"baseline"}


# --- GET /review/queue -------------------------------------------------------------------


def test_queue_orders_by_priority_and_excludes_settled_notes(api, llm) -> None:
    calm = post_note(api, llm, "API-5", "AM call. All well, breakfast eaten.", reply())
    medium = post_note(
        api,
        llm,
        "API-6",
        "Only ate half of lunch, encouraged fluids.",
        reply(("nutrition_hydration", "Only ate half of lunch", "medium", 0.5)),
    )
    high = post_note(api, llm, "API-7", FALL_TEXT, FALL_REPLY)

    queue = api.get("/review/queue").json()
    ids = [q["note_id"] for q in queue]
    assert calm["id"] not in ids
    assert ids.index(high["id"]) < ids.index(medium["id"])  # high first, though newer
    item = queue[ids.index(high["id"])]
    assert item["priority"] == "high"
    assert [f["category"] for f in item["pending_flags"]] == ["falls"]  # auto-accepted hidden
    assert api.get("/review/queue", params={"limit": 1}).json()[0]["note_id"] == high["id"]


# --- POST /review/{flag_id} --------------------------------------------------------------


def test_approve_settles_note_and_writes_audit_event(api, llm, as_manager) -> None:
    note = post_note(api, llm, "API-8", FALL_TEXT, FALL_REPLY)
    falls = flag(note, "falls")
    r = api.post(
        f"/review/{falls['id']}",
        json={"action": "approve", "comment": "Rang Mrs Sampleton's daughter"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["flag"]["review_status"] == "approved"
    assert out["diff"] == {"review_status": {"before": "pending", "after": "approved"}}
    assert out["note_review_required"] is False  # last pending flag
    assert note["id"] not in [q["note_id"] for q in api.get("/review/queue").json()]

    trail = api.get(f"/audit/{note['id']}", headers=as_manager).json()
    last = trail[-1]
    assert (last["event_type"], last["actor"]) == ("review_decision", "user:coord.alpha")
    assert last["output"]["has_comment"] is True
    assert "Sampleton" not in json.dumps(trail)  # the comment stays out of the audit log


def test_edit_stores_diff_and_regrounds_evidence(api, llm, db_session) -> None:
    note = post_note(api, llm, "API-9", FALL_TEXT, FALL_REPLY)
    falls = flag(note, "falls")
    edit = {"severity": "medium", "evidence": "found on the floor"}  # lower case: normalised
    r = api.post(f"/review/{falls['id']}", json={"action": "edit", "edit": edit})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["flag"]["evidence"] == "Found on the floor"  # the note's own text, not typed
    assert out["flag"]["grounding_status"] == "normalised"
    assert set(out["diff"]) == {
        "severity",
        "evidence",
        "span_end",
        "grounding_status",
        "review_status",
    }
    assert out["diff"]["severity"] == {"before": "high", "after": "medium"}

    decision = db_session.scalars(select(ReviewDecisionRecord)).one()
    assert decision.reviewer == "coord.alpha"
    assert decision.before["severity"] == "high"
    assert decision.after["severity"] == "medium"


def test_reviewer_can_reject_an_auto_accepted_flag(api, llm) -> None:
    note = post_note(api, llm, "API-10", FALL_TEXT, FALL_REPLY)
    meds = flag(note, "medication")
    r = api.post(f"/review/{meds['id']}", json={"action": "reject"})
    assert r.status_code == 200
    assert r.json()["flag"]["review_status"] == "rejected"
    assert r.json()["note_review_required"] is True  # falls still pending


@pytest.mark.parametrize(
    "body",
    [
        {"action": "edit", "edit": {"evidence": "client was dancing in the garden"}},  # ungrounded
        {"action": "edit", "edit": {"severity": "high"}},  # no actual change
        {"action": "edit", "edit": {}},  # empty edit
        {"action": "edit"},  # edit missing
        {"action": "approve", "edit": {"severity": "low"}},  # edit on non-edit action
        {"action": "escalate"},  # unknown action
    ],
)
def test_invalid_review_is_422_and_changes_nothing(api, llm, body, as_manager) -> None:
    note = post_note(api, llm, "API-11", FALL_TEXT, FALL_REPLY)
    falls = flag(note, "falls")
    r = api.post(f"/review/{falls['id']}", json=body)
    assert r.status_code == 422, r.text
    after = api.get(f"/notes/{note['id']}").json()
    assert flag(after, "falls") == falls
    assert (
        api.get(f"/audit/{note['id']}", headers=as_manager).json()[-1]["event_type"]
        == "flags_routed"
    )


def test_second_decision_on_same_flag_is_409(api, llm) -> None:
    note = post_note(api, llm, "API-12", FALL_TEXT, FALL_REPLY)
    url = f"/review/{flag(note, 'falls')['id']}"
    assert api.post(url, json={"action": "approve"}).status_code == 200
    again = api.post(url, json={"action": "reject"})
    assert again.status_code == 409
    assert "approved" in again.json()["detail"]


def test_reviewer_identity_comes_from_the_token_not_the_client(api, llm, db_session) -> None:
    """The old prototype header is ignored: a client can't claim to be someone else."""
    note = post_note(api, llm, "API-13", FALL_TEXT, FALL_REPLY)
    r = api.post(
        f"/review/{flag(note, 'falls')['id']}",
        json={"action": "approve"},
        headers={"X-Reviewer": "manager.alpha"},
    )
    assert r.status_code == 200, r.text
    decision = db_session.scalar(select(ReviewDecisionRecord))
    assert decision.reviewer == "coord.alpha"


def test_review_unknown_flag_is_404(api) -> None:
    r = api.post(f"/review/{uuid4()}", json={"action": "approve"})
    assert r.status_code == 404


# --- GET /audit/{note_id} ----------------------------------------------------------------


def test_audit_trail_is_ordered_and_404_for_unknown(api, llm, as_manager) -> None:
    note = post_note(api, llm, "API-14", FALL_TEXT, FALL_REPLY)
    trail = api.get(f"/audit/{note['id']}", headers=as_manager).json()
    assert [e["event_type"] for e in trail] == [
        "note_ingested",
        "pii_redacted",
        "extraction_completed",
        "baseline_completed",
        "flags_routed",
    ]
    assert trail[2]["prompt_version"] == "extraction/v2"
    assert api.get(f"/audit/{uuid4()}", headers=as_manager).status_code == 404


def test_review_locks_the_flag_row(api, llm, db_session) -> None:
    """Two coordinators deciding one flag at once: the second waits on the row lock, then
    sees the first decision and gets 409. Checked here by the SQL emitted."""
    note = post_note(api, llm, "API-15", FALL_TEXT, FALL_REPLY)
    statements: list[str] = []
    conn = db_session.connection()
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(conn, "before_cursor_execute", listener)
    try:
        api.post(f"/review/{flag(note, 'falls')['id']}", json={"action": "approve"})
    finally:
        event.remove(conn, "before_cursor_execute", listener)
    assert any("FROM risk_flags" in s and "FOR UPDATE" in s for s in statements)
