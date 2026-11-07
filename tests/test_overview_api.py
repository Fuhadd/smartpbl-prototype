"""GET /overview: one summary per panel of the coordinator overview (Main.dc.html)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_llm_client
from app.audit.models import AuditEvent, EventType
from app.auth.models import Role
from app.core.db import get_session
from app.main import app
from app.matching.presets import Preset, preset_for
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


def test_empty_day_has_no_rates_and_no_schedule(api) -> None:
    body = api.get("/overview").json()
    assert body["review"] == {"awaiting_flags": 0, "awaiting_high": 0, "notes_waiting": 0,
                              "attention": []}  # fmt: skip
    assert body["flags_by_category"]["counts"] == []
    p = body["pipeline"]
    assert p["extractions"] == 0 and p["schema_valid_rate"] is None and p["model_name"] is None
    assert body["schedule"] is None  # never invent a rota


def test_review_panels_reflect_a_new_note(api, llm) -> None:
    note = post_note(api, llm, "OV-1", FALL_TEXT, FALL_REPLY)
    body = api.get("/overview").json()
    r = body["review"]
    # The medium medication flag is grounded and confident, so it was auto-accepted.
    assert r["awaiting_flags"] == 1 and r["awaiting_high"] == 1 and r["notes_waiting"] == 1
    top = r["attention"][0]
    assert top["note_id"] == note["id"] and top["client_ref"] == "CL-0099"
    assert (top["category"], top["severity"]) == ("falls", "high")
    assert top["evidence"] == "Found on the floor by the bed"
    counts = {c["category"]: c["count"] for c in body["flags_by_category"]["counts"]}
    assert counts == {"falls": 1, "medication": 1}
    p = body["pipeline"]
    assert p["extractions"] == 1 and p["schema_valid_rate"] == 1.0
    assert p["grounded_rate"] == 1.0 and p["model_name"] == "fake-model:1b"


def test_rejected_flags_drop_out_of_the_category_counts(api, llm) -> None:
    note = post_note(api, llm, "OV-2", FALL_TEXT, FALL_REPLY)
    decisions = [{"flag_id": f["id"], "action": "reject"} for f in note["flags"]
                 if f["review_status"] == "pending"]  # fmt: skip
    assert api.post(f"/review/notes/{note['id']}", json={"decisions": decisions}).status_code == 200
    body = api.get("/overview").json()
    # The falls flag was rejected; the auto-accepted medication flag still counts.
    assert body["flags_by_category"]["counts"] == [{"category": "medication", "count": 1}]
    assert body["review"]["awaiting_flags"] == 0


def test_schedule_summary_compares_with_the_greedy_baseline(api) -> None:
    assert post(api, small_scenario()).status_code == 201
    s = api.get("/overview").json()["schedule"]
    assert s["preset"] == "balanced"
    assert (s["visits"], s["served"], s["unassigned"], s["carers_on_shift"]) == (4, 2, 2, 2)
    assert s["baseline"]["solver"] == "greedy"
    assert s["baseline"]["served"] == 1  # greedy serves one fewer visit here
    assert s["first_unassigned"]["visit_id"].startswith("V-")


def test_workforce_summary_counts_the_support_group_and_is_audited(api, db_session) -> None:
    w = api.get("/overview").json()["workforce"]
    assert (w["elevated"], w["total"]) == (40, 200)  # top 20% of the 200 current carers
    assert w["check_in"]["carer_ref"].startswith("WF-")
    viewed = db_session.scalars(
        select(AuditEvent).where(AuditEvent.event_type == EventType.WORKFORCE_RISK_VIEWED)
    ).all()
    assert [e.output for e in viewed] == [
        {"carer_refs": [w["check_in"]["carer_ref"]], "view": "overview"}
    ]
    assert viewed[0].actor == "user:coord.alpha"


def test_attention_notes_are_audited_as_a_queue_view(api, llm, db_session) -> None:
    note = post_note(api, llm, "OV-3", FALL_TEXT, FALL_REPLY)
    api.get("/overview")
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == EventType.REVIEW_QUEUE_VIEWED)
    )
    assert event.output == {"note_ids": [note["id"]], "view": "overview"}


PRESET_CASES = [
    (0, Preset.TRAVEL),
    (15, Preset.BALANCED),
    (30, Preset.CONTINUITY),
    (45, Preset.CUSTOM),  # dominated in the sweep (ADR-033)
    (20, Preset.CUSTOM),
]


@pytest.mark.parametrize(("weight", "preset"), PRESET_CASES)
def test_presets_name_the_continuity_weights(weight, preset) -> None:
    assert preset_for(weight) is preset
