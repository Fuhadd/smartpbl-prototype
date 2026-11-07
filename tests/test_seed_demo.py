"""Demo accounts match the sign-in screen and only exist in demo environments."""

from sqlalchemy import select

from app.auth.models import Role, User
from app.auth.service import authenticate
from scripts import seed_demo


def test_seed_creates_the_design_accounts_and_is_idempotent(db_session) -> None:
    first = seed_demo.seed(db_session)
    again = seed_demo.seed(db_session)
    assert [line.split()[0] for line in first] == ["created"] * 3
    assert [line.split()[0] for line in again] == ["reset"] * 3
    hannah = authenticate(db_session, "hannah@demo.smartpbl", "demo-coordinator")
    assert hannah is not None and hannah.role is Role.COORDINATOR
    assert hannah.display_name == "Hannah K."
    roles = {u.username: u.role for u in db_session.scalars(select(User))}
    assert roles["sam@demo.smartpbl"] is Role.MANAGER
    assert roles["joy@demo.smartpbl"] is Role.CARER


def test_seed_refuses_outside_demo_environments(monkeypatch, capsys) -> None:
    class Prod:
        environment = "production"

    monkeypatch.setattr(seed_demo, "get_settings", lambda: Prod())
    assert seed_demo.main() == 1
    assert "Refusing" in capsys.readouterr().err
