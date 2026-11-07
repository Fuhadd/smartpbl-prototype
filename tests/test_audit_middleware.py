"""Unified audit: one api_request row per routed call, correlated with domain events by
request id, auth outcomes recorded, reads fail closed. Real app, test Postgres."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.audit.middleware as middleware
from app.api.deps import get_llm_client
from app.audit.log import input_hash
from app.audit.models import AuditEvent, EventType, SubjectType
from app.auth.models import Role
from app.core.db import get_session
from app.main import ROUTERS, app
from tests.conftest import TEST_PASSWORD
from tests.fakes import FakeClient
from tests.test_api import FALL_REPLY, FALL_TEXT, post_note


@pytest.fixture
def llm() -> FakeClient:
    return FakeClient([])


@pytest.fixture
def api(db_session, llm) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_llm_client] = lambda: llm
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def requests(db_session) -> list[AuditEvent]:
    return list(
        db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == EventType.API_REQUEST)
            .order_by(AuditEvent.id)
        )
    )


def test_every_routed_call_gets_one_row_and_a_request_id(api, auth_headers, db_session):
    api.headers.update(auth_headers(Role.MANAGER))
    note_id = "00000000-0000-4000-8000-000000000001"
    r = api.get(f"/notes/{note_id}")
    assert r.status_code == 404
    [row] = requests(db_session)
    assert str(row.request_id) == r.headers["x-request-id"]
    assert row.actor == "user:manager.alpha"
    assert (row.subject_type, row.subject_id) == (SubjectType.CARE_NOTE, note_id)
    # The route template, never the raw path or query string.
    assert row.output["route"] == "/notes/{note_id}" and row.output["status"] == 404
    assert row.output["duration_ms"] >= 0


def test_health_and_unrouted_paths_are_not_audited(api, db_session) -> None:
    assert "x-request-id" in api.get("/health").headers
    assert api.get("/no-such-path").status_code == 404
    assert requests(db_session) == []


def test_domain_events_share_the_request_id_of_the_call(api, llm, auth_headers, db_session):
    """The model's decisions (actor system:pipeline) link to the human who triggered them."""
    api.headers.update(auth_headers(Role.COORDINATOR))
    note = post_note(api, llm, "MW-1", FALL_TEXT, FALL_REPLY)
    events = db_session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    note_events = [e for e in events if e.note_id is not None and str(e.note_id) == note["id"]]
    [call] = [e for e in events if e.request_id == note_events[0].request_id
              and e.event_type is EventType.API_REQUEST]  # fmt: skip
    assert {e.request_id for e in note_events} == {call.request_id}
    assert {e.actor for e in note_events} == {"system:pipeline"}
    assert call.actor == "user:coord.alpha" and call.output["status"] == 201
    assert all(e.subject_type is SubjectType.CARE_NOTE for e in note_events)


@pytest.mark.parametrize(
    ("role", "actor", "status"),
    [(Role.CARER, "user:carer.alpha", 403), (None, "anonymous", 401)],
)
def test_refusals_are_recorded(api, auth_headers, db_session, role, actor, status) -> None:
    headers = auth_headers(role) if role else {}
    assert api.get("/review/queue", headers=headers).status_code == status
    [row] = requests(db_session)
    assert (row.actor, row.output["status"]) == (actor, status)


def test_login_outcomes_are_recorded_with_a_hashed_username(api, auth_headers, db_session):
    auth_headers(Role.COORDINATOR)  # creates coord.alpha
    bad = api.post("/auth/token", data={"username": "coord.alpha", "password": "wrong-pass"})
    good = api.post("/auth/token", data={"username": "coord.alpha", "password": TEST_PASSWORD})
    assert (bad.status_code, good.status_code) == (401, 200)
    failed, ok = requests(db_session)
    assert failed.actor == "anonymous" and failed.output["status"] == 401
    assert ok.actor == "user:coord.alpha" and ok.output["status"] == 200
    assert failed.input_hash == ok.input_hash == input_hash("coord.alpha")
    assert "coord.alpha" not in str(failed.output)


def test_refresh_reuse_is_a_recorded_security_event(api, auth_headers, db_session) -> None:
    auth_headers(Role.COORDINATOR)
    login = api.post("/auth/token", data={"username": "coord.alpha", "password": TEST_PASSWORD})
    stolen = login.json()["refresh_token"]
    assert api.post("/auth/refresh", json={"refresh_token": stolen}).status_code == 200
    assert api.post("/auth/refresh", json={"refresh_token": stolen}).status_code == 401
    [alert] = db_session.scalars(
        select(AuditEvent).where(AuditEvent.event_type == EventType.REFRESH_TOKEN_REUSE_DETECTED)
    ).all()
    assert alert.actor == "system:auth" and alert.subject_type is SubjectType.USER
    assert alert.request_id == requests(db_session)[-1].request_id


def test_queue_views_and_note_reads_appear_in_the_note_trail(api, llm, auth_headers):
    """'Who has seen this note?' is answerable from GET /audit/{note_id}."""
    api.headers.update(auth_headers(Role.COORDINATOR))
    note = post_note(api, llm, "MW-2", FALL_TEXT, FALL_REPLY)
    api.get("/review/queue")
    manager = auth_headers(Role.MANAGER)
    api.get(f"/notes/{note['id']}", headers=manager)
    trail = api.get(f"/audit/{note['id']}", headers=manager).json()
    seen = [(e["event_type"], e["actor"], (e["output"] or {}).get("route")) for e in trail]
    assert ("review_queue_viewed", "user:coord.alpha", None) in seen
    assert ("api_request", "user:coord.alpha", "/review/queue") in seen
    assert ("api_request", "user:manager.alpha", "/notes/{note_id}") in seen


def _broken_record(*args, **kwargs):
    raise RuntimeError("audit database unavailable")


def test_reads_fail_closed_when_the_audit_write_fails(api, llm, auth_headers, monkeypatch):
    api.headers.update(auth_headers(Role.COORDINATOR))
    note = post_note(api, llm, "MW-3", FALL_TEXT, FALL_REPLY)
    monkeypatch.setattr(middleware, "record", _broken_record)
    r = api.get(f"/notes/{note['id']}")
    assert r.status_code == 500
    assert r.json() == {"detail": "audit log unavailable; response withheld"}
    assert "floor" not in r.text and "x-request-id" in r.headers


def test_writes_return_their_real_outcome_when_the_access_row_fails(
    api, llm, auth_headers, monkeypatch
):
    """The change and its domain events already committed together; a 500 would be a lie."""
    api.headers.update(auth_headers(Role.COORDINATOR))
    monkeypatch.setattr(middleware, "record", _broken_record)
    note = post_note(api, llm, "MW-4", FALL_TEXT, FALL_REPLY)  # asserts 201
    assert note["external_id"] == "MW-4"


def test_every_path_parameter_maps_to_a_subject_type() -> None:
    """A new route with an id in its path must say what kind of subject the id names."""
    params = {p.name for r in ROUTERS for route in r.routes for p in route.dependant.path_params}
    assert params <= set(middleware.SUBJECT_PARAMS), params - set(middleware.SUBJECT_PARAMS)
