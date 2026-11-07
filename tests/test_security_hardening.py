"""Step 4.3 hardening: secrets refused outside local, rate limits, body-size limit,
security headers, CORS and input bounds."""

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_llm_client
from app.auth.models import Role
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.http import SecurityHeadersMiddleware
from app.core.ratelimit import SlidingWindowLimiter
from app.main import app
from tests.conftest import TEST_PASSWORD
from tests.fakes import FakeClient
from tests.test_api import FALL_REPLY

STRONG = "s" * 64


@pytest.fixture
def api(db_session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_llm_client] = lambda: FakeClient([FALL_REPLY] * 10)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# --- secrets and configuration ------------------------------------------------------------


def test_local_accepts_development_defaults() -> None:
    assert Settings(environment="local").is_local


def test_non_local_refuses_every_insecure_default_at_once() -> None:
    with pytest.raises(ValidationError) as e:
        Settings(environment="production", jwt_secret="short", cors_origins=["*"])
    msg = str(e.value)
    assert "shorter than 32 bytes" in msg
    assert "AUDIT_HASH_KEY is the public development default" in msg
    assert "not '*'" in msg


def test_non_local_refuses_the_public_jwt_default() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET is the public development default"):
        Settings(environment="staging", audit_hash_key=STRONG)


def test_non_local_with_real_secrets_starts_without_docs() -> None:
    """A fresh interpreter, as a deployment would start: docs off, settings accepted."""
    env = {**os.environ, "SMARTPBL_ENVIRONMENT": "production",
           "SMARTPBL_JWT_SECRET": STRONG, "SMARTPBL_AUDIT_HASH_KEY": STRONG}  # fmt: skip
    code = "from app.main import app; print(app.docs_url, app.openapi_url)"
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.split() == ["None", "None"]
    env["SMARTPBL_JWT_SECRET"] = "short"
    bad = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert bad.returncode != 0 and "refusing to start" in bad.stderr


# --- rate limiting ------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_sliding_window_refuses_then_recovers() -> None:
    clock = FakeClock()
    lim = SlidingWindowLimiter("t", lambda: 3, window_s=60, clock=clock)
    for _ in range(3):
        lim.check("k")
        clock.now += 10
    with pytest.raises(Exception) as e:  # 4th within 60 s of the first
        lim.check("k")
    assert e.value.status_code == 429
    assert e.value.headers["Retry-After"] == "30"  # first hit leaves the window in 30 s
    lim.check("other")  # keys are independent
    clock.now += 30  # first hit expires; refused attempts weren't counted
    lim.check("k")


def _login(api, username: str, password: str = "wrong-password"):
    return api.post("/auth/token", data={"username": username, "password": password})


def test_login_is_limited_per_username_even_with_the_right_password(api, auth_headers):
    auth_headers(Role.COORDINATOR)
    assert [_login(api, "coord.alpha").status_code for _ in range(5)] == [401] * 5
    blocked = _login(api, "COORD.alpha", TEST_PASSWORD)  # case-folded: same key
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert _login(api, "manager.alpha").status_code == 401  # other accounts unaffected


def test_login_is_limited_per_ip_across_usernames(api, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "login_limit_per_ip", 3)
    codes = [_login(api, f"nobody.{i}").status_code for i in range(4)]
    assert codes == [401, 401, 401, 429]


def test_solver_and_note_submission_are_limited_per_user(api, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "solve_limit_per_user", 1)
    monkeypatch.setattr(get_settings(), "note_limit_per_user", 1)
    api.headers.update(auth_headers(Role.COORDINATOR))
    quick = {"time_limit_s": 0.5, "continuity_weight_min": 0}  # the sample day, briefly
    assert api.post("/schedule/solve", json=quick).status_code == 201
    assert api.post("/schedule/solve", json={"time_limit_s": 1}).status_code == 429
    note = {"note_id": "RL-1", "client_ref": "CL-1", "carer_ref": "CR-1",
            "visit_time": "2026-01-05T09:00:00Z", "text": "All well today."}  # fmt: skip
    assert api.post("/notes", json=note).status_code == 201
    assert api.post("/notes", json={**note, "note_id": "RL-2"}).status_code == 429


# --- request size, headers, CORS ----------------------------------------------------------


def test_oversized_bodies_are_refused_declared_or_chunked(api) -> None:
    big = b"x" * (get_settings().max_body_bytes + 1)
    declared = api.post("/notes", content=big, headers={"content-type": "application/json"})
    assert declared.status_code == 413

    def chunks() -> Iterator[bytes]:
        yield big

    chunked = api.post("/auth/token", content=chunks(),
                       headers={"content-type": "application/x-www-form-urlencoded"})  # fmt: skip
    assert chunked.status_code == 413


def test_api_responses_carry_security_headers(api) -> None:
    h = api.get("/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["cache-control"] == "no-store"
    assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert h["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in h  # local: plain HTTP
    assert "content-security-policy" not in api.get("/docs").headers  # Swagger needs scripts


def test_hsts_is_sent_when_enabled() -> None:
    tiny = FastAPI()
    tiny.get("/")(lambda: {})
    tiny.add_middleware(SecurityHeadersMiddleware, hsts=True)
    assert "max-age=31536000" in TestClient(tiny).get("/").headers["strict-transport-security"]


def test_cors_allows_listed_origins_only_and_never_credentials(api) -> None:
    preflight = {"access-control-request-method": "POST",
                 "access-control-request-headers": "authorization"}  # fmt: skip
    ok = api.options("/notes", headers={"origin": "http://localhost:5173", **preflight})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in ok.headers
    evil = api.options("/notes", headers={"origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in evil.headers
    simple = api.get("/health", headers={"origin": "http://localhost:5173"})
    assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()


# --- input bounds -------------------------------------------------------------------------


@pytest.mark.parametrize("bad_id", ["N" * 51, "N-1; DROP", "", "../etc"])
def test_note_ids_are_bounded_identifiers(api, auth_headers, bad_id) -> None:
    """An 80-character id used to reach the database and fail with a 500."""
    note = {"note_id": bad_id, "client_ref": "CL-1", "carer_ref": "CR-1",
            "visit_time": "2026-01-05T09:00:00Z", "text": "All well."}  # fmt: skip
    assert api.post("/notes", json=note, headers=auth_headers(Role.COORDINATOR)).status_code == 422


def test_carerless_scenario_is_refused_not_a_process_crash(api, auth_headers) -> None:
    """Regression: zero carers = zero vehicles, and OR-Tools aborted the whole process."""
    empty = {"name": "x", "seed": 1, "carers": [], "clients": [], "visits": []}
    r = api.post("/schedule/solve", json={"scenario": empty},
                 headers=auth_headers(Role.COORDINATOR))  # fmt: skip
    assert r.status_code == 422 and "at least one carer" in r.text


def test_caller_supplied_scenarios_are_size_capped(api, auth_headers) -> None:
    visit = {"client_ref": "CL-0001", "window_start": 480, "window_end": 540, "duration": 30,
             "required_skills": ["personal_care"]}  # fmt: skip
    visits = [{**visit, "visit_id": f"V-{i:04d}"} for i in range(401)]
    body = {"scenario": {"name": "big", "seed": 1, "carers": [], "clients": [], "visits": visits}}
    r = api.post("/schedule/solve", json=body, headers=auth_headers(Role.COORDINATOR))
    assert r.status_code == 422 and "at most 400 visits" in r.text


def test_validation_errors_do_not_echo_submitted_values(api, auth_headers) -> None:
    secret_text = "Mrs Sampleton fell in the kitchen at ZZ3 4AB."
    note = {"note_id": "bad id!", "client_ref": "CL-1", "carer_ref": "CR-1",
            "visit_time": "2026-01-05T09:00:00Z", "text": secret_text}  # fmt: skip
    r = api.post("/notes", json=note, headers=auth_headers(Role.COORDINATOR))
    assert r.status_code == 422
    [err] = r.json()["detail"]
    assert err["loc"] == ["body", "note_id"] and "pattern" in err["msg"]
    assert "Sampleton" not in r.text and "bad id!" not in r.text
