"""Database fixtures: a separate `<db>_test` database, migrated with Alembic once per run,
with each test in a transaction that is rolled back afterwards.

If Postgres is unreachable, DB tests are skipped. Set SMARTPBL_REQUIRE_DB=1 (as CI will)
to make that a failure instead.
"""

import os
from collections.abc import Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth.models import Role
from app.auth.service import create_user, issue_tokens
from app.core.config import get_settings


def _test_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session")
def test_db_url() -> str:
    admin_url = get_settings().database_url
    url = _test_url()
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            name = make_url(url).database
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name})
            if not exists.scalar():
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
    except OperationalError as e:
        if os.environ.get("SMARTPBL_REQUIRE_DB") == "1":
            raise
        pytest.skip(
            f"Postgres not reachable ({e.__class__.__name__}); run `docker compose up -d db`"
        )
    cfg = alembic_config(url)
    command.downgrade(cfg, "base")  # clean slate: also proves downgrade works
    command.upgrade(cfg, "head")
    return url


@pytest.fixture(scope="session")
def engine(test_db_url: str) -> Iterator[Engine]:
    eng = create_engine(test_db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is always rolled back. Code under test may
    commit or use savepoints; nothing persists between tests."""
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


# Obviously synthetic accounts, one per role; tests expect these names in audit rows.
USERNAMES = {
    Role.COORDINATOR: "coord.alpha",
    Role.MANAGER: "manager.alpha",
    Role.CARER: "carer.alpha",
}
TEST_PASSWORD = "synthetic-test-password"

AuthHeaders = Callable[[Role], dict[str, str]]


@pytest.fixture
def auth_headers(db_session: Session) -> AuthHeaders:
    """`auth_headers(Role.MANAGER)` -> a Bearer header for that role's test user, created
    on first use inside the rolled-back test transaction."""
    cache: dict[Role, dict[str, str]] = {}

    def make(role: Role) -> dict[str, str]:
        if role not in cache:
            user = create_user(db_session, USERNAMES[role], TEST_PASSWORD, role)
            token = issue_tokens(db_session, user).access_token
            # Commit = release the savepoint; the outer test transaction still rolls it all
            # back. Without it, an endpoint's own rollback() would discard the user.
            db_session.commit()
            cache[role] = {"Authorization": f"Bearer {token}"}
        return cache[role]

    return make
