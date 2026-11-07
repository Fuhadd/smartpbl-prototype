"""Auth and RBAC: login, refresh rotation and reuse detection, revocation, and the
route x role permission matrix. Real routers, test Postgres."""

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_workforce
from app.auth.models import RefreshToken, Role, User
from app.auth.service import create_user, issue_tokens
from app.core.db import get_session
from app.main import ROUTERS, app
from tests.conftest import TEST_PASSWORD, USERNAMES

C, M, W = Role.COORDINATOR, Role.MANAGER, Role.CARER
PUBLIC = {("GET", "/health"), ("POST", "/auth/token"), ("POST", "/auth/refresh"),
          ("POST", "/auth/logout")}  # fmt: skip

# The policy, written out independently of ROLE_PERMISSIONS (so the test isn't circular).
# Each request is cheap for an allowed role: it fails validation (422) or finds nothing
# (404) after authorisation has passed.
MATRIX: list[tuple[str, str, str, dict, set[Role]]] = [
    ("POST", "/notes", "/notes", {"json": {}}, {W, C}),
    ("GET", "/notes/{note_id}", f"/notes/{uuid4()}", {}, {C, M}),
    ("GET", "/review/queue", "/review/queue", {}, {C, M}),
    ("POST", "/review/{flag_id}", f"/review/{uuid4()}", {"json": {}}, {C}),
    ("POST", "/review/notes/{note_id}", f"/review/notes/{uuid4()}", {"json": {}}, {C}),
    ("GET", "/audit/{note_id}", f"/audit/{uuid4()}", {}, {C, M}),
    ("GET", "/audit", "/audit", {"params": {"limit": 0}}, {C, M}),
    ("GET", "/audit/summary", "/audit/summary", {}, {C, M}),
    ("GET", "/audit/export", "/audit/export", {"params": {"kind": "nope"}}, {C, M}),
    ("GET", "/overview", "/overview", {}, {C, M}),
    ("POST", "/schedule/solve", "/schedule/solve", {"json": {"time_limit_s": -1}}, {C}),
    ("GET", "/schedule/{run_id}", f"/schedule/{uuid4()}", {}, {C, M}),
    ("GET", "/schedule/latest", "/schedule/latest", {}, {C, M}),
    ("GET", "/schedule/tradeoff", "/schedule/tradeoff", {}, {C, M}),
    ("GET", "/schedule/{run_id}/map", f"/schedule/{uuid4()}/map", {}, {C, M}),
    ("GET", "/workforce/risk", "/workforce/risk", {"params": {"limit": 0}}, {C, M}),
    ("GET", "/workforce/{carer_ref}/explanation", "/workforce/CR-0001/explanation", {}, {C, M}),
    ("GET", "/auth/me", "/auth/me", {}, {C, M, W}),
]


@pytest.fixture
def api(db_session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def users(auth_headers) -> None:
    for role in Role:
        auth_headers(role)  # creates the three test users


def login(api, role: Role = C, password: str = TEST_PASSWORD):
    return api.post("/auth/token", data={"username": USERNAMES[role], "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- login and identity ------------------------------------------------------------------


def test_login_returns_tokens_and_me_reflects_role(api, users) -> None:
    r = login(api, M)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    me = api.get("/auth/me", headers=bearer(body["access_token"])).json()
    assert me["username"] == "manager.alpha" and me["role"] == "manager"
    assert "workforce.read" in me["permissions"] and "review.decide" not in me["permissions"]


def test_bad_credentials_all_look_the_same(api, users, db_session) -> None:
    """Unknown user, wrong password and disabled account: identical 401s (no enumeration)."""
    db_session.scalar(select(User).where(User.username == "carer.alpha")).is_active = False
    db_session.commit()
    responses = [
        login(api, C, password="wrong-password"),
        api.post("/auth/token", data={"username": "nobody.zz", "password": TEST_PASSWORD}),
        login(api, W),  # disabled
    ]
    assert {r.status_code for r in responses} == {401}
    assert len({r.text for r in responses}) == 1
    assert all(r.headers["www-authenticate"] == "Bearer" for r in responses)


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Basic Zm9vOmJhcg=="}],
)
def test_protected_routes_need_a_valid_bearer_token(api, headers) -> None:
    r = api.get("/review/queue", headers=headers)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_refresh_token_is_not_an_access_token(api, users) -> None:
    refresh = login(api).json()["refresh_token"]
    assert api.get("/auth/me", headers=bearer(refresh)).status_code == 401


def test_disabling_or_demoting_takes_effect_immediately(api, users, db_session) -> None:
    """Authorisation reads the user's current state, not the role baked into the token."""
    access = login(api, C).json()["access_token"]
    user = db_session.scalar(select(User).where(User.username == "coord.alpha"))
    user.role = Role.CARER
    db_session.commit()
    assert api.get("/review/queue", headers=bearer(access)).status_code == 403
    user.is_active = False
    db_session.commit()
    assert api.get("/auth/me", headers=bearer(access)).status_code == 401


# --- refresh rotation, reuse detection, logout -------------------------------------------


def test_refresh_rotates_and_old_token_is_single_use(api, users, db_session) -> None:
    first = login(api).json()
    second = api.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200, second.text
    new = second.json()
    assert new["refresh_token"] != first["refresh_token"]
    assert api.get("/auth/me", headers=bearer(new["access_token"])).status_code == 200
    old = db_session.scalar(select(RefreshToken).where(RefreshToken.replaced_by.is_not(None)))
    current = db_session.get(RefreshToken, old.replaced_by)
    assert old.revoked_at is not None and current.revoked_at is None
    assert old.family_id == current.family_id


def test_reusing_a_rotated_refresh_token_revokes_the_family(api, users) -> None:
    """Reuse means two parties hold the token (one stole it). We can't tell which is
    legitimate, so the whole session dies, including the attacker's fresh token."""
    stolen = login(api).json()["refresh_token"]
    legit = api.post("/auth/refresh", json={"refresh_token": stolen}).json()["refresh_token"]
    replay = api.post("/auth/refresh", json={"refresh_token": stolen})
    assert replay.status_code == 401
    assert api.post("/auth/refresh", json={"refresh_token": legit}).status_code == 401


def test_logout_revokes_the_session_but_not_other_sessions(api, users) -> None:
    phone, laptop = login(api).json(), login(api).json()

    def post(path: str, session: dict) -> int:
        return api.post(path, json={"refresh_token": session["refresh_token"]}).status_code

    assert post("/auth/logout", phone) == 204
    assert post("/auth/refresh", phone) == 401
    assert post("/auth/refresh", laptop) == 200


def test_refresh_for_disabled_account_fails(api, users, db_session) -> None:
    refresh = login(api).json()["refresh_token"]
    db_session.scalar(select(User).where(User.username == "coord.alpha")).is_active = False
    db_session.commit()
    assert api.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401


# --- RBAC matrix -------------------------------------------------------------------------


def _operations() -> dict[tuple[str, str], dict]:
    """Every operation, from the public OpenAPI schema (app.routes hides included routers
    behind lazy wrappers in this FastAPI version, so walking it would miss them)."""
    paths = app.openapi()["paths"]
    return {(m.upper(), p): op for p, ops in paths.items() for m, op in ops.items()}


def _permissions(route: APIRoute) -> list:
    stack, found = list(route.dependant.dependencies), []
    while stack:
        d = stack.pop()
        if hasattr(d.call, "required_permission"):
            found.append(d.call.required_permission)
        stack.extend(d.dependencies)
    return found


def test_every_non_public_route_requires_identity_and_a_permission() -> None:
    """Guard against a new endpoint shipping without access control."""
    ops = _operations()
    routes = {(m, r.path): r for router in ROUTERS for r in router.routes for m in r.methods}
    assert set(routes) | {("GET", "/health")} == set(ops)  # no router left out of ROUTERS
    for key, op in ops.items():
        if key in PUBLIC:
            continue
        assert op.get("security") == [{"OAuth2PasswordBearer": []}], key
        if key != ("GET", "/auth/me"):  # identity only: any role may ask who it is
            assert _permissions(routes[key]), f"{key} has no require(...) dependency"


def test_matrix_covers_every_route() -> None:
    assert {(m, p) for m, p, *_ in MATRIX} | PUBLIC == set(_operations())


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(("method", "template", "url", "kwargs", "allowed"), MATRIX,
                         ids=[f"{m} {t}" for m, t, *_ in MATRIX])  # fmt: skip
def test_role_permission_matrix(api, auth_headers, role, method, template, url, kwargs, allowed):
    # Never train the model here: an empty stand-in scored workforce.
    app.dependency_overrides[get_workforce] = lambda: SimpleNamespace(
        ranked=lambda: [], version="stub", carers={}
    )
    r = api.request(method, url, headers=auth_headers(role), **kwargs)
    if role in allowed:
        assert r.status_code not in (401, 403), (role, template, r.text)
    else:
        assert r.status_code == 403, (role, template, r.text)
        assert r.json() == {"detail": "insufficient permissions"}


@pytest.mark.parametrize(("method", "template", "url", "kwargs", "allowed"), MATRIX,
                         ids=[f"{m} {t}" for m, t, *_ in MATRIX])  # fmt: skip
def test_unauthenticated_is_401_everywhere(api, method, template, url, kwargs, allowed):
    assert api.request(method, url, **kwargs).status_code == 401


def test_authorisation_runs_before_expensive_dependencies(api, auth_headers) -> None:
    """A carer asking for workforce risk is refused before the model is touched."""
    called = []
    app.dependency_overrides[get_workforce] = lambda: called.append(1)
    assert api.get("/workforce/risk", headers=auth_headers(W)).status_code == 403
    assert called == []


def test_me_includes_display_name(api, db_session) -> None:
    user = create_user(db_session, "hannah.zz", TEST_PASSWORD, C, display_name="Hannah K.")
    db_session.commit()
    token = issue_tokens(db_session, user).access_token
    me = api.get("/auth/me", headers=bearer(token)).json()
    assert me["display_name"] == "Hannah K." and me["role"] == "coordinator"
