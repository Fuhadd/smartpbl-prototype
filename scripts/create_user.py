"""Create a SMARTPBL user account.

    uv run python -m scripts.create_user coord.demo coordinator

The password is prompted for (never a command-line argument, which would land in shell
history and the process list). Pipe it on stdin for automation: `--password-stdin`.
Use obviously synthetic usernames only.
"""

import argparse
import getpass
import sys

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import Role
from app.auth.service import create_user
from app.core.db import get_engine

MIN_PASSWORD_LENGTH = 12  # NCSC/NIST guidance favours length over composition rules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("username", help="e.g. coord.demo (letters, digits, . _ -)")
    parser.add_argument("role", choices=[r.value for r in Role])
    parser.add_argument("--password-stdin", action="store_true", help="read password from stdin")
    args = parser.parse_args()

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat: "):
            print("Passwords differ.", file=sys.stderr)
            return 1
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1

    with Session(get_engine()) as session:
        try:
            create_user(session, args.username, password, Role(args.role))
            session.commit()
        except IntegrityError:
            print(f"User {args.username!r} already exists.", file=sys.stderr)
            return 1
    print(f"Created {args.role} {args.username!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
