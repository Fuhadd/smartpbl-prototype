"""Schedule API and explanations: real router + test Postgres; small scenarios use the
haversine fallback (no cached matrix), the committed sample uses its cached OSRM matrix."""

import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit.log import input_hash
from app.audit.models import AuditEvent, EventType
from app.auth.models import Role
from app.core.db import get_session
from app.main import app
from app.matching.data import Client, Scenario, Skill
from app.matching.explain import DropReason, explain
from app.matching.service import resolve_matrix
from app.matching.solver import SolverParams, solve
from tests.test_solver import FAR, NEAR, OFFICE, carer, client, visit


def small_scenario() -> Scenario:
    """Two carers; one client prefers CR-0002; one catheter visit nobody can do; two
    overlapping visits for CR-0001's skill so one must be dropped for capacity."""
    near = carer("CR-0001", {Skill.MEDICATION}).model_copy(update={"start": NEAR, "home": NEAR})
    far = carer("CR-0002").model_copy(update={"start": FAR, "home": FAR})
    clients = [
        Client(
            client_ref="CL-0001",
            location=OFFICE,
            needs=frozenset({Skill.PERSONAL_CARE, Skill.CATHETER_CARE, Skill.MEDICATION}),
            preferred_carers=("CR-0002",),
            recent_carers=("CR-0002",),
        ),
        client("CL-0002", NEAR, {Skill.MEDICATION}),
    ]
    visits = [
        visit("V-0001", "CL-0001", 480, 540),
        visit("V-0002", "CL-0001", 600, 620, skills=[Skill.CATHETER_CARE]),  # nobody can
        visit("V-0003", "CL-0002", 480, 480, dur=60, skills=[Skill.MEDICATION]),
        visit("V-0004", "CL-0001", 480, 480, dur=60, skills=[Skill.MEDICATION]),  # clashes
    ]
    return Scenario(name="api-test", seed=7, carers=(near, far), clients=tuple(clients),
                    visits=tuple(visits))  # fmt: skip


@pytest.fixture
def api(db_session, auth_headers) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app, headers=auth_headers(Role.COORDINATOR)) as client:
        yield client
    app.dependency_overrides.clear()


def post(api, scenario: Scenario | None, **params):
    body = {"time_limit_s": 1.0, "continuity_weight_min": 15, **params}
    if scenario is not None:
        body["scenario"] = json.loads(scenario.model_dump_json())
    return api.post("/schedule/solve", json=body)


def test_explanations_give_reasons_and_drop_causes() -> None:
    s = small_scenario()
    m = resolve_matrix(s)
    assert m.backend.startswith("haversine")  # not cached: fallback
    sol = solve(s, m, SolverParams(time_limit_s=1.0, continuity_weight_s=1800))
    assigned, dropped = explain(s, m, sol)
    reasons = {d.visit_id: d for d in dropped}
    assert reasons["V-0002"].reason is DropReason.NO_ELIGIBLE_CARER
    assert "catheter_care" in reasons["V-0002"].detail
    busy = [d for d in dropped if d.reason is DropReason.ELIGIBLE_CARERS_BUSY]
    assert len(busy) == 1 and busy[0].eligible_carers == ["CR-0001"]
    v1 = next(a for a in assigned if a.visit_id == "V-0001")
    assert v1.carer_ref == "CR-0002" and "Client's preferred carer" in v1.reasons
    assert any(r.startswith("Arrives 08:") and "08:00-09:00 window" in r for r in v1.reasons)
    assert v1.other_eligible == 1


def test_solve_persists_run_with_reasons_and_audit(api, db_session) -> None:
    s = small_scenario()
    r = post(api, s)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["metrics"] == {
        "visits": 4,
        "served": 2,
        "dropped": 2,
        "familiar_pct": 0.5,
        "preferred_pct": 0.5,
        "distinct_carers_per_client": 0.0,
        "carers_used": 2,
        # Greedy on the same day: no look-ahead, so the clash costs it a second visit.
        "baseline": {"solver": "greedy", "travel_s": 140, "served": 1, "familiar_pct": 0.0},
    }
    assert {d["reason"] for d in out["dropped"]} == {
        "no_eligible_carer",
        "eligible_carers_busy",
    }
    assert out["params"]["two_phase"] is True and out["matrix_backend"].startswith("haversine")
    assert out["scenario_hash"] == input_hash(s.model_dump_json())
    assert all(v["reasons"] for route in out["routes"] for v in route["visits"])

    again = api.get(f"/schedule/{out['id']}")
    assert again.status_code == 200 and again.json() == out

    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.event_type == EventType.SCHEDULE_SOLVED)
    ).one()
    assert event.actor == "user:coord.alpha"
    assert event.output["run_id"] == out["id"]
    assert event.output["scenario_seed"] == 7
    assert event.model_name == "ortools"
    dumped = json.dumps(event.output)
    assert "52.4" not in dumped and "lat" not in dumped  # no locations in the audit log


def test_invalid_scenario_is_422_with_problems(api) -> None:
    s = small_scenario()
    broken = s.model_copy(update={"visits": (*s.visits[:1], visit("V-0009", "CL-9999", 480, 540))})
    r = post(api, broken)
    assert r.status_code == 422
    assert any("unknown client" in p for p in r.json()["detail"]["problems"])


@pytest.mark.parametrize(
    "params", [{"time_limit_s": 100}, {"continuity_weight_min": -1}, {"surprise": True}]
)
def test_parameter_limits(api, params) -> None:
    assert post(api, small_scenario(), **params).status_code == 422


def test_unknown_run_is_404(api) -> None:
    assert api.get(f"/schedule/{uuid4()}").status_code == 404


@pytest.mark.slow
def test_sample_scenario_uses_cached_osrm_matrix(api) -> None:
    r = post(api, None, continuity_weight_min=0)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["matrix_backend"].startswith("osrm:car:")
    assert out["metrics"]["visits"] == 106
    assert out["params"]["two_phase"] is False


# --- Step 5.3: next best carer, latest run, map and trade-off -----------------------------


def test_next_best_names_the_closest_other_qualified_carer() -> None:
    s = small_scenario()
    m = resolve_matrix(s)
    sol = solve(s, m, SolverParams(time_limit_s=1.0, continuity_weight_s=1800))
    assigned, _ = explain(s, m, sol)
    v1 = next(a for a in assigned if a.visit_id == "V-0001")
    # Continuity won: the preferred (far) carer got it, so the alternative is the nearer,
    # unfamiliar one, and its travel difference is negative.
    assert v1.alternative is not None
    assert v1.alternative["carer_ref"] == "CR-0001"
    assert v1.alternative["familiarity"] == "new"
    assert v1.alternative["extra_travel_min"] < 0
    # Nobody else can do a medication visit CR-0001 got (CR-0002 lacks the skill).
    v3 = next(a for a in assigned if a.visit_id in ("V-0003", "V-0004"))
    assert v3.alternative is None


def test_latest_returns_the_newest_run(api) -> None:
    assert api.get("/schedule/latest").status_code == 404
    first = post(api, small_scenario()).json()
    second = post(api, small_scenario(), continuity_weight_min=0).json()
    latest = api.get("/schedule/latest").json()
    assert latest["id"] == second["id"] != first["id"]
    v1 = next(a for r in latest["routes"] for a in r["visits"] if a["visit_id"] == "V-0001")
    assert set(v1["alternative"]) == {"carer_ref", "extra_travel_min", "familiarity"}


def test_map_is_only_served_for_the_sample_scenario(api) -> None:
    custom = post(api, small_scenario()).json()
    r = api.get(f"/schedule/{custom['id']}/map")
    assert r.status_code == 404 and "sample scenario" in r.json()["detail"]
    sample = post(api, None, time_limit_s=1.0).json()
    body = api.get(f"/schedule/{sample['id']}/map").json()
    assert body["scenario_name"] == "birmingham-day-seed42"
    assert len(body["carers"]) == 17 and len(body["visits"]) == 106
    lat, lon = body["visits"][0]["location"].values()
    assert 52.3 < lat < 52.6 and -2.1 < lon < -1.7  # the Birmingham bounding box
    served = {a["visit_id"] for r in sample["routes"] for a in r["visits"]}
    assert served <= {v["visit_id"] for v in body["visits"]}


def test_tradeoff_presets_sit_on_the_pareto_front(api) -> None:
    body = api.get("/schedule/tradeoff").json()
    assert body["presets"] == {"travel": 0, "balanced": 15, "continuity": 30}
    by_w = {p["weight_min"]: p for p in body["points"]}
    assert all(by_w[w]["pareto"] for w in body["presets"].values())
    assert by_w[45]["pareto"] is False  # why Continuity is 30, not 45 (ADR-033)
    assert by_w[30]["familiar_pct"] > by_w[15]["familiar_pct"] > by_w[0]["familiar_pct"]
