"""visit audit subject

Adds `visit` to the audit subject types, so carer-app reads of /me/visits/{visit_id} are
recorded against the visit by the audit middleware (CHECK constraint edited by hand).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-07 16:30:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_SUBJECTS = ("care_note", "risk_flag", "schedule_run", "carer", "user")
_NEW_SUBJECTS = (*_OLD_SUBJECTS, "visit")
_CK = "ck_audit_events_subjecttype"


def _subject_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(_CK), "audit_events", type_="check")
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(op.f(_CK), "audit_events", f"subject_type IN ({allowed})")


def upgrade() -> None:
    _subject_check(_NEW_SUBJECTS)


def downgrade() -> None:
    """Fails if any audit row is about a visit (the audit log is append-only)."""
    _subject_check(_OLD_SUBJECTS)
