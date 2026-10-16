"""Initial schema: users, instruments, alerts, device tokens, notifications.

Seeds the NIFTY 50 instrument.

Revision ID: 0001
Revises:
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("firebase_uid", sa.String(128), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(200)),
        sa.Column("photo_url", sa.String(1000)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("firebase_uid", name="uq_users_firebase_uid"),
    )

    instruments = op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False),
        sa.Column("instrument_type", sa.String(10), nullable=False),
        sa.Column("angelone_exchange_type", sa.SmallInteger()),
        sa.Column("angelone_token", sa.String(32)),
        sa.Column("yahoo_symbol", sa.String(32)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_instruments"),
        sa.UniqueConstraint("symbol", name="uq_instruments_symbol"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(8), nullable=False),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2)),
        sa.Column("status", sa.String(12), server_default="active", nullable=False),
        sa.Column("note", sa.String(200)),
        sa.Column("triggered_at", sa.DateTime(timezone=True)),
        sa.Column("triggered_price", sa.Numeric(12, 2)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_alerts_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name="fk_alerts_instrument_id_instruments",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("condition IN ('above', 'below')", name="ck_alerts_condition_valid"),
        sa.CheckConstraint(
            "status IN ('active', 'triggered', 'cancelled')", name="ck_alerts_status_valid"
        ),
        sa.CheckConstraint("target_price > 0", name="ck_alerts_target_positive"),
    )
    op.create_index(
        "ix_alerts_active_lookup",
        "alerts",
        ["instrument_id", "condition", "target_price"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_alerts_user_status", "alerts", ["user_id", "status"])

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_device_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token", name="uq_device_tokens_token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid()),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("status", sa.String(12), server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_notifications_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            name="fk_notifications_alert_id_alerts",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name="ck_notifications_status_valid"
        ),
    )
    op.create_index("ix_notifications_status_created", "notifications", ["status", "created_at"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    # NIFTY 50: Angel One token 99926000 on NSE (exchange type 1), Yahoo symbol ^NSEI.
    op.bulk_insert(
        instruments,
        [
            {
                "symbol": "NIFTY50",
                "name": "NIFTY 50",
                "exchange": "NSE",
                "instrument_type": "INDEX",
                "angelone_exchange_type": 1,
                "angelone_token": "99926000",
                "yahoo_symbol": "^NSEI",
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("device_tokens")
    op.drop_table("alerts")
    op.drop_table("instruments")
    op.drop_table("users")
