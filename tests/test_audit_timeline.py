"""GET /audit, /audit/summary and /audit/export: the grouped timeline of the raw log."""

import csv
import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.audit import _cell
from app.api.deps import get_llm_client
from app.audit.models import AuditEvent
from app.audit.timeline import fingerprint
from app.auth.models import Role
from app.core.db import get_session
from app.main import app
from tests.fakes import FakeClient
from tests.test_api import FALL_REPLY, FALL_TEXT, post_note
from tests.test_schedule_api import post, small_scenario


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


def entries(api, **params) -> list[dict]:
    r = api.get("/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()["entries"]


def pending(note: dict) -> list[dict]:
    return [f for f in note["flags"] if f["review_status"] == "pending"]


def details(entry: dict) -> dict[str, dict]:
    return {d["label"]: d for d in entry["details"]}


def test_one_note_becomes_submitted_and_ai_output_entries(api, llm, db_session) -> None:
    note = post_note(api, llm, "AT-1", FALL_TEXT, FALL_REPLY)
    ai, submitted = entries(api)  # newest first
    assert submitted["kind"] == "note_submitted"
    assert submitted["actor"] == {"kind": "user", "name": "coord.alpha", "role": "coordinator"}
    assert submitted["subject"] == "CL-0099 · care note" and submitted["note_id"] == note["id"]
    assert submitted["result"].endswith("identifiers redacted")
    assert ai["kind"] == "ai_output" and ai["actor"]["name"] == "System"
    assert ai["version"].startswith("fake-model:1b · prompt ")
    assert ai["result"] == "2 flags · routed to review"
    assert details(ai)["Grounding and routing"]["value"] == "2 flags · 2 / 2 grounded"
    # Every entry traces back to raw rows, and raw rows aren't hidden by grouping.
    types = {e.id: e.event_type.value for e in db_session.query(AuditEvent)}
    assert sorted(types[i] for i in submitted["event_ids"]) == ["note_ingested", "pii_redacted"]
    assert sorted(types[i] for i in ai["event_ids"]) == ["extraction_completed", "flags_routed"]


def test_a_note_decision_is_one_entry_linked_to_its_ai_output(api, llm) -> None:
    note = post_note(api, llm, "AT-2", FALL_TEXT, FALL_REPLY)
    decisions = [{"flag_id": f["id"], "action": "approve"} for f in pending(note)]
    body = {"decisions": decisions, "escalate": True}
    assert api.post(f"/review/notes/{note['id']}", json=body).status_code == 200
    decision = entries(api, kind="human_decision")
    assert len(decision) == 1
    d = decision[0]
    assert d["result"] == "Approved · escalated"
    tiles = details(d)
    assert tiles["Decision"]["value"] == "Approved 1 flag unchanged"
    assert tiles["Decision"]["secondary"] == "Escalated to care manager (falls, high)"
    assert tiles["Linked AI output"]["secondary"] == "2 flags · 2 / 2 grounded"
    assert tiles["Input fingerprint"]["value"].startswith("hmac-sha256:")
    assert tiles["Reviewer changes"]["value"] == "None"


def test_edits_show_as_a_diff_and_count_as_overrides(api, llm) -> None:
    note = post_note(api, llm, "AT-3", FALL_TEXT, FALL_REPLY)
    falls = pending(note)[0]
    edit = [{"flag_id": falls["id"], "action": "edit", "edit": {"severity": "medium"}}]
    assert api.post(f"/review/notes/{note['id']}", json={"decisions": edit}).status_code == 200
    d = entries(api, kind="human_decision")[0]
    assert d["result"] == "1 edited"
    assert details(d)["Reviewer changes"]["value"] == "Falls: severity high → medium"
    summary = api.get("/audit/summary").json()
    assert summary["human_overrides"] == 1
    # Routed as high, so it counts as a high flag decided by a person, even though edited down.
    assert (summary["high_flags_today"], summary["high_flags_reviewed"]) == (1, 1)


def test_denied_requests_appear_under_access(api, auth_headers) -> None:
    assert api.get("/workforce/risk", headers=auth_headers(Role.CARER)).status_code == 403
    (denied,) = entries(api, kind="access")
    assert denied["kind"] == "access_denied" and denied["result"] == "Role lacks permission"
    assert denied["subject"] == "Workforce risk"
    assert denied["actor"] == {"kind": "user", "name": "carer.alpha", "role": "carer"}
    assert api.get("/audit/summary").json()["access_denied"] == 1


def test_successful_reads_are_logged_but_not_shown(api) -> None:
    api.get("/review/queue")
    api.get("/overview")
    assert entries(api) == []
    assert api.get("/audit/summary").json()["entries_today"] > 0


def test_schedule_runs_name_preset_seed_and_assignment(api) -> None:
    assert post(api, small_scenario()).status_code == 201
    (run,) = entries(api, kind="schedule_run")
    assert run["version"] == "OR-Tools · balanced · seed 7"
    assert run["result"] == "2 / 4 assigned" and run["subject"] == "Rota · api-test"


def test_keyset_pages_never_repeat_or_skip(api, llm) -> None:
    for i in range(3):
        post_note(api, llm, f"AT-P{i}", FALL_TEXT, FALL_REPLY)
    everything = [e["id"] for e in entries(api, limit=200)]
    assert len(everything) == 6
    seen, before = [], None
    while True:
        params = {"limit": 4} | ({"before": before} if before else {})
        page = api.get("/audit", params=params).json()
        seen += [e["id"] for e in page["entries"]]
        before = page["next_before"]
        if before is None:
            break
    assert seen == everything


def test_search_by_client_or_user_and_wildcards_are_literal(api, llm, auth_headers) -> None:
    post_note(api, llm, "AT-S", FALL_TEXT, FALL_REPLY)
    api.get("/workforce/risk", headers=auth_headers(Role.CARER))
    assert len(entries(api, q="cl-0099")) == 2  # case-insensitive client ref
    assert [e["kind"] for e in entries(api, q="carer.alpha")] == ["access_denied"]
    # The submitter is found through the request that carried the note.
    assert "note_submitted" in [e["kind"] for e in entries(api, q="coord.alpha")]
    assert entries(api, q="%") == [] and entries(api, q="_") == []


def test_export_is_csv_of_the_filtered_timeline(api, llm) -> None:
    post_note(api, llm, "AT-E", FALL_TEXT, FALL_REPLY)
    r = api.get("/audit/export", params={"kind": "ai_output"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["time_utc", "event", "actor", "subject", "version", "result", "event_ids"]
    assert [row[1] for row in rows[1:]] == ["ai_output"]


@pytest.mark.parametrize(
    "value", ["=HYPERLINK(1)", "+1", "-1", "@SUM(A1)", "\tx", "\nx", "\uff1dSUM(A1)"]
)
def test_export_cells_cannot_start_a_formula(value) -> None:
    assert _cell(value).startswith("'")


def test_fingerprint_shows_algorithm_and_ends() -> None:
    assert fingerprint("hmac-sha256", "3f9a" + "0" * 56 + "c71e") == "hmac-sha256:3f9a…c71e"
    assert fingerprint(None, None) == "—"


def test_carers_cannot_read_the_timeline(api, auth_headers) -> None:
    for path in ("/audit", "/audit/summary", "/audit/export"):
        assert api.get(path, headers=auth_headers(Role.CARER)).status_code == 403
