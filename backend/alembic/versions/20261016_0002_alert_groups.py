"""High & low (range) alerts: group alerts together, optional one-cancels-other.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.add_column(
        "alerts",
        sa.Column(
            "one_cancels_other", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_index(
        "ix_alerts_group_id",
        "alerts",
        ["group_id"],
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_group_id", table_name="alerts")
    op.drop_column("alerts", "one_cancels_other")
    op.drop_column("alerts", "group_id")
