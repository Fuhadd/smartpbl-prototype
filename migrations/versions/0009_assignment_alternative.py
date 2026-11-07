"""assignment next-best alternative

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable: runs saved before Step 5.3 have no counterfactual, and some visits have no
    # other qualified carer.
    op.add_column(
        "schedule_assignments",
        sa.Column("alternative", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("schedule_assignments", "alternative")
