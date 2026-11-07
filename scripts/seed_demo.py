"""Create (or reset) the three public demo accounts shown on the sign-in screen.

    uv run python -m scripts.seed_demo

The credentials are published on the login page by design, so they are not secrets.
That is also why this script refuses to run unless SMARTPBL_ENVIRONMENT is "local" or
"demo": public passwords must never exist in a real deployment. They are also shorter
than the 12-character minimum that `create_user` enforces for real accounts.
Re-running resets their passwords, roles and names to these values.
"""

import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Role, User
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.security import hash_password

DEMO_ENVIRONMENTS = frozenset({"local", "demo"})


@dataclass(frozen=True)
class DemoAccount:
    username: str
    password: str
    role: Role
    display_name: str
    carer_ref: str | None = None  # carer logins act as one carer on the sample rota


# Copy matches docs/design/screens/Login.dc.html ("Demo accounts"). Obviously synthetic.
DEMO_ACCOUNTS = (
    DemoAccount("hannah@demo.smartpbl", "demo-coordinator", Role.COORDINATOR, "Hannah K."),
    DemoAccount("sam@demo.smartpbl", "demo-manager", Role.MANAGER, "Sam R."),
    # CR-0001: a full, mostly familiar round on the sample day (about 6 visits).
    DemoAccount("joy@demo.smartpbl", "demo-carer", Role.CARER, "Joy A.", "CR-0001"),
)


def seed(session: Session) -> list[str]:
    """Upsert the demo accounts; returns what was done, one line per account."""
    done = []
    for acct in DEMO_ACCOUNTS:
        user = session.scalar(select(User).where(User.username == acct.username))
        verb = "reset" if user else "created"
        if user is None:
            user = User(username=acct.username)
            session.add(user)
        user.password_hash = hash_password(acct.password)
        user.role = acct.role
        user.display_name = acct.display_name
        user.carer_ref = acct.carer_ref
        user.is_active = True
        done.append(f"{verb} {acct.role.value:<11} {acct.username}")
    session.flush()
    return done


def main() -> int:
    env = get_settings().environment
    if env not in DEMO_ENVIRONMENTS:
        print(f"Refusing to seed public demo accounts in environment {env!r}.", file=sys.stderr)
        return 1
    with Session(get_engine()) as session:
        lines = seed(session)
        session.commit()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
