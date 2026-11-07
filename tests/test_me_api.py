"""Carer app API (Step 5.6): own rota only, own notes only, need-to-know client notes."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_llm_client
from app.audit.models import AuditEvent, EventType
from app.auth.models import Role, User
from app.core.db import get_session
from app.main import app
from app.matching.models import ScheduleAssignment, ScheduleRun
from app.matching.runs import sample_scenario
from tests.conftest import USERNAMES
from tests.fakes import FakeClient
from tests.test_api import FALL_REPLY, reply


@pytest.fixture
def llm() -> FakeClient:
    return FakeClient([])


@pytest.fixture
def carer(auth_headers) -> dict[str, str]:
    """The carer test user, linked to CR-0001 (conftest), as the demo seed links Joy."""
    return auth_headers(Role.CARER)


@pytest.fixture
def api(db_session, llm) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_llm_client] = lambda: llm
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _sample_visits(n: int):
    scenario, _ = sample_scenario()
    return [v for v in scenario.visits][:n]


@pytest.fixture
def run(db_session) -> ScheduleRun:
    """A saved run of the sample day: CR-0001 gets two visits, CR-0002 one."""
    _, digest = sample_scenario()
    v1, v2, v3 = _sample_visits(3)
    run = ScheduleRun(
        scenario_name="birmingham-day-seed42", scenario_seed=42, scenario_hash=digest,
        solver="test", params={}, status="ROUTING_SUCCESS", objective=0, travel_s=1200,
        wall_s=0.1, matrix_backend="test", metrics={}, dropped=[], requested_by="user:coord",
        created_at=datetime.now(UTC),
    )  # fmt: skip
    for seq, (carer_ref, v, travel) in enumerate(
        [("CR-0001", v1, 540), ("CR-0001", v2, 660), ("CR-0002", v3, 300)], 1
    ):
        start = v.window_start * 60
        run.assignments.append(
            ScheduleAssignment(
                carer_ref=carer_ref, sequence=seq if carer_ref == "CR-0001" else 1,
                visit_id=v.visit_id, client_ref=v.client_ref, start_s=start,
                end_s=start + v.duration * 60, travel_s=travel, familiarity="preferred",
                reasons=[], alternative=None,
            )
        )  # fmt: skip
    db_session.add(run)
    db_session.commit()
    return run


def _note(visit, **over) -> dict:
    return {
        "note_id": f"N-{visit.visit_id}",
        "client_ref": visit.client_ref,
        "carer_ref": "CR-0001",
        "visit_id": visit.visit_id,
        "visit_time": "2026-11-07T09:00:00Z",
        "text": "Synthetic visit note. All well, ate breakfast.",
        **over,
    }


def test_visits_are_the_carers_own_route_with_tasks_and_place(api, carer, run) -> None:
    body = api.get("/me/visits", headers=carer).json()
    v1, v2, _ = _sample_visits(3)
    assert body["carer_ref"] == "CR-0001"
    assert [v["visit_id"] for v in body["visits"]] == [v1.visit_id, v2.visit_id]
    assert body["summary"] == {"visits": 2, "done": 0, "travel_min": 20}
    first = body["visits"][0]
    assert first["window_start_min"] == v1.window_start
    assert first["duration_min"] == v1.duration
    keys = [t["key"] for t in first["tasks"]]
    assert set(keys) == {s.value for s in v1.required_skills}
    assert keys[-1] == "personal_care"  # specialist tasks first
    assert 52.3 < first["location"]["lat"] < 52.6
    assert first["note"] is None


def test_no_rota_is_404_and_unlinked_login_is_403(api, carer, auth_headers, db_session) -> None:
    assert api.get("/me/visits", headers=carer).status_code == 404
    user = db_session.scalar(select(User).where(User.username == USERNAMES[Role.CARER]))
    user.carer_ref = None
    db_session.commit()
    assert api.get("/me/visits", headers=carer).status_code == 403


def test_coordinators_have_no_carer_rota(api, auth_headers, run) -> None:
    assert api.get("/me/visits", headers=auth_headers(Role.COORDINATOR)).status_code == 403


def test_visit_detail_is_own_rota_only_and_audits_client_notes(
    api, carer, run, llm, db_session
) -> None:
    v1, _, v3 = _sample_visits(3)
    # Another carer's visit, and a made-up one, look the same: not on your rota.
    assert api.get(f"/me/visits/{v3.visit_id}", headers=carer).status_code == 404
    assert api.get("/me/visits/V-9999", headers=carer).status_code == 404
    llm.replies.append(FALL_REPLY)
    note = _note(v1, text="Found on the floor by the bed. Refused her tablets.")
    assert api.post("/notes", json=note, headers=carer).status_code == 201
    body = api.get(f"/me/visits/{v1.visit_id}", headers=carer).json()
    assert body["note"]["note_id"] == f"N-{v1.visit_id}"
    [recent] = body["recent_notes"]
    assert {f["category"] for f in recent["flags"]} == {"falls", "medication"}
    assert recent["review_required"] is True
    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.event_type == EventType.CLIENT_NOTES_VIEWED)
    ).one()
    assert event.output["client_ref"] == v1.client_ref
    assert event.output["note_ids"] == [recent["note_id"]]


def test_submitted_note_marks_the_visit_done(api, carer, run, llm) -> None:
    v1, _, _ = _sample_visits(3)
    llm.replies.append(reply())
    api.post("/notes", json=_note(v1, tasks_done=["personal_care"]), headers=carer)
    body = api.get("/me/visits", headers=carer).json()
    assert body["summary"]["done"] == 1
    assert body["visits"][0]["note"]["urgent"] is False


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"carer_ref": "CR-0002"}, "own notes"),
        ({"visit_id": None}, "rota"),
        ({"visit_id": "V-0999"}, "rota"),
        ({"client_ref": "CL-0999"}, "rota"),
    ],
)
def test_carer_can_only_write_own_notes_for_own_visits(api, carer, run, over, why) -> None:
    v1, _, _ = _sample_visits(3)
    r = api.post("/notes", json=_note(v1, **over), headers=carer)
    assert r.status_code == 403 and why in r.json()["detail"]


def test_another_carers_visit_is_refused(api, carer, run) -> None:
    _, _, v3 = _sample_visits(3)  # CR-0002's visit
    r = api.post("/notes", json=_note(v3), headers=carer)
    assert r.status_code == 403


def test_urgent_note_goes_to_the_top_of_the_review_queue(
    api, carer, run, llm, auth_headers
) -> None:
    v1, v2, _ = _sample_visits(3)
    coord = auth_headers(Role.COORDINATOR)
    llm.replies.append(FALL_REPLY)  # a high-severity flag, not urgent
    api.post("/notes", json=_note(v1, text="Found on the floor by the bed."), headers=carer)
    llm.replies.append(reply())  # no flags at all, but the carer raised a concern
    created = api.post("/notes", json=_note(v2, urgent=True), headers=carer).json()
    assert created["urgent"] is True and created["review_required"] is True
    queue = api.get("/review/queue", headers=coord).json()
    assert [q["external_id"] for q in queue] == [f"N-{v2.visit_id}", f"N-{v1.visit_id}"]
    assert queue[0]["priority"] == "high" and queue[0]["pending_flags"] == []
    # With nothing to decide, the coordinator acknowledges it, which clears it from review.
    r = api.post(f"/review/notes/{created['id']}", json={"decisions": []}, headers=coord)
    assert r.status_code == 200 and r.json()["note"]["review_required"] is False
