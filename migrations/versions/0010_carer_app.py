"""carer app

Links carer logins to their scheduling identity (users.carer_ref), records which visit a
note is for, the carer's urgent-concern switch and the tasks ticked, and adds the
client_notes_viewed audit event (CHECK constraint edited by hand, as in 0008).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-07 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_EVENTS = (
    "note_ingested",
    "pii_redacted",
    "extraction_completed",
    "extraction_failed",
    "baseline_completed",
    "flags_routed",
    "review_decision",
    "schedule_solved",
    "workforce_risk_viewed",
    "workforce_explanation_viewed",
    "api_request",
    "review_queue_viewed",
    "refresh_token_reuse_detected",
    "review_escalated",
)
_NEW_EVENTS = (*_OLD_EVENTS, "client_notes_viewed")
_CK = "ck_audit_events_eventtype"


def _event_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(_CK), "audit_events", type_="check")
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(op.f(_CK), "audit_events", f"event_type IN ({allowed})")


def upgrade() -> None:
    _event_check(_NEW_EVENTS)
    op.add_column("users", sa.Column("carer_ref", sa.String(length=20), nullable=True))
    op.create_unique_constraint(op.f("uq_users_carer_ref"), "users", ["carer_ref"])
    op.add_column("care_notes", sa.Column("visit_id", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_care_notes_visit_id"), "care_notes", ["visit_id"])
    op.add_column(
        "care_notes",
        sa.Column("urgent", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "care_notes",
        sa.Column("tasks_done", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Fails if client_notes_viewed events exist (the audit log is append-only)."""
    _event_check(_OLD_EVENTS)
    op.drop_column("care_notes", "tasks_done")
    op.drop_column("care_notes", "urgent")
    op.drop_index(op.f("ix_care_notes_visit_id"), table_name="care_notes")
    op.drop_column("care_notes", "visit_id")
    op.drop_constraint(op.f("uq_users_carer_ref"), "users", type_="unique")
    op.drop_column("users", "carer_ref")
