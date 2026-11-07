"""Workforce API: real router, real (cached) model, test Postgres for the audit log."""

import math
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit.models import AuditEvent, EventType
from app.auth.models import Role
from app.core.db import get_session
from app.main import app
from app.workforce.service import get_workforce_risk, model_version

FORBIDDEN = ("left_within_12m", "age_band", "18-24", "55+")


@pytest.fixture
def api(db_session, auth_headers) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app, headers=auth_headers(Role.MANAGER)) as client:
        yield client
    app.dependency_overrides.clear()


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def test_risk_list_ranked_paged_and_supportive(api) -> None:
    r = api.get("/workforce/risk")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 200 and len(body["carers"]) == 20
    risks = [c["risk"] for c in body["carers"]]
    assert risks == sorted(risks, reverse=True)
    assert [c["rank"] for c in body["carers"]] == list(range(1, 21))
    assert body["carers"][0]["carer_ref"] == "WF-0461"  # the 3.3 waterfall carer
    assert "Supportive use only" in body["use_notice"]
    assert body["model"]["synthetic"] is True
    assert all(len(c["top_factors"]) == 3 for c in body["carers"])
    page2 = api.get("/workforce/risk", params={"offset": 20, "limit": 5}).json()
    assert [c["rank"] for c in page2["carers"]] == [21, 22, 23, 24, 25]


def test_priority_only_returns_top_fifth(api) -> None:
    body = api.get("/workforce/risk", params={"priority_only": True, "limit": 200}).json()
    assert body["total"] == 40
    assert all(c["support_priority"] for c in body["carers"])


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_risk_list_validates_paging(api, params) -> None:
    assert api.get("/workforce/risk", params=params).status_code == 422


def test_explanation_adds_up_and_offers_support_only_for_raising_levers(api) -> None:
    body = api.get("/workforce/WF-0461/explanation").json()
    assert body["rank"] == 1 and body["of"] == 200
    assert len(body["factors"]) == 12
    total = sum(f["log_odds"] for f in body["factors"])
    assert total == pytest.approx(_logit(body["risk"]) - _logit(body["baseline_risk"]), abs=0.05)
    for f in body["factors"]:
        assert (f["support"] is None) == (f["direction"] == "lowers")
    raising_levers = [f["support"] for f in body["factors"] if f["provider_can_change"]
                      and f["direction"] == "raises" and f["log_odds"] >= 0.1]  # fmt: skip
    assert body["suggested_support"] == list(dict.fromkeys(raising_levers))
    assert body["suggested_support"][0] == "give more rota notice and limit late changes"
    assert "review round size" not in body["suggested_support"]  # tiny contribution
    assert body["baseline_risk"] < body["average_risk"]  # sigmoid(mean) < mean(sigmoid)


def test_explanation_points_add_up_to_the_score_and_compare_with_team(api) -> None:
    body = api.get("/workforce/WF-0461/explanation").json()
    points = [f["points"] for f in body["factors"]]
    gap = 100 * (body["risk"] - body["baseline_risk"])
    assert sum(points) == pytest.approx(gap, abs=0.3)  # 3 dp rounding of the two risks
    assert all((p > 0) == (f["log_odds"] > 0) for p, f in zip(points, body["factors"], strict=True))
    team = {f["feature"]: f["team_value"] for f in body["factors"]}
    assert team["drive_min_per_shift"].endswith(" min")
    assert team["zero_hours"].endswith("% of team")


def test_responses_never_include_label_or_protected_attribute(api) -> None:
    texts = [
        api.get("/workforce/risk", params={"limit": 200}).text,
        api.get("/workforce/WF-0461/explanation").text,
    ]
    for text in texts:
        for word in FORBIDDEN:
            assert word not in text


def test_explanation_errors(api) -> None:
    assert api.get("/workforce/WF-9999/explanation").status_code == 404
    assert api.get("/workforce/CR-0001/explanation").status_code == 422


def test_every_read_is_audited(api, db_session) -> None:
    api.get("/workforce/risk", params={"limit": 3})
    api.get("/workforce/WF-0461/explanation")
    events = db_session.scalars(
        select(AuditEvent)
        .where(AuditEvent.event_type.in_([EventType.WORKFORCE_RISK_VIEWED,
                                           EventType.WORKFORCE_EXPLANATION_VIEWED]))
        .order_by(AuditEvent.id)
    ).all()  # fmt: skip
    listed, explained = events
    assert listed.actor == explained.actor == "user:manager.alpha"
    assert listed.output["carer_refs"] == ["WF-0461", *listed.output["carer_refs"][1:]]
    assert len(listed.output["carer_refs"]) == 3
    assert explained.output["carer_ref"] == "WF-0461"
    assert explained.model_version == get_workforce_risk().version


def test_model_version_tracks_training_data(tmp_path) -> None:
    a = tmp_path / "a.csv"
    a.write_text("x\n1\n")
    b = tmp_path / "b.csv"
    b.write_text("x\n2\n")
    assert model_version(a) != model_version(b)
    assert model_version(a) == model_version(a)
