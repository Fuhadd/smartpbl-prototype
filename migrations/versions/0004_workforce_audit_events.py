"""workforce audit events

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07 12:00:00

Hand-written: autogenerate does not detect new values in a VARCHAR + CHECK enum.
No tables: workforce risk is computed in memory; only reads are recorded, in audit_events.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
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
)
_NEW_EVENTS = (*_OLD_EVENTS, "workforce_risk_viewed", "workforce_explanation_viewed")
_CK = "ck_audit_events_eventtype"


def _event_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(_CK), "audit_events", type_="check")
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(op.f(_CK), "audit_events", f"event_type IN ({allowed})")


def upgrade() -> None:
    _event_check(_NEW_EVENTS)


def downgrade() -> None:
    """Fails if workforce view events exist: the audit log is append-only, so downgrading
    must not silently invalidate recorded events."""
    _event_check(_OLD_EVENTS)
