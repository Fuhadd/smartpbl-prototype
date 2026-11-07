"""audit subject and request id

Adds a generic subject (type + id) and a request id to audit events, and the Step 4.2
event types. Existing rows are not backfilled: the table is append-only (a trigger rejects
UPDATE), and rewriting history to fit a new schema is what an audit log must not do.
Older note events keep matching by `note_id`.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07 09:01:55.715712

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
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
)
_NEW_EVENTS = (*_OLD_EVENTS, "api_request", "review_queue_viewed", "refresh_token_reuse_detected")
_CK = "ck_audit_events_eventtype"
_SUBJECTS = ("care_note", "risk_flag", "schedule_run", "carer", "user")


def _event_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(_CK), "audit_events", type_="check")
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(op.f(_CK), "audit_events", f"event_type IN ({allowed})")


def upgrade() -> None:
    _event_check(_NEW_EVENTS)
    subject_type = sa.Enum(
        *_SUBJECTS, name="subjecttype", native_enum=False, create_constraint=True, length=30
    )
    op.add_column("audit_events", sa.Column("subject_type", subject_type, nullable=True))
    op.add_column("audit_events", sa.Column("subject_id", sa.String(length=100), nullable=True))
    op.add_column("audit_events", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_audit_events_request_id"), "audit_events", ["request_id"])
    op.create_index("ix_audit_events_subject", "audit_events", ["subject_type", "subject_id"])


def downgrade() -> None:
    """Restores the old event CHECK first, so it fails (and the transactional DDL rolls
    back) if any Step 4.2 events exist: dropping their columns would destroy audit data."""
    _event_check(_OLD_EVENTS)
    op.drop_index("ix_audit_events_subject", table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_request_id"), table_name="audit_events")
    op.drop_column("audit_events", "request_id")
    op.drop_column("audit_events", "subject_id")
    op.drop_column("audit_events", "subject_type")
