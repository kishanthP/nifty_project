import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.instrument import Instrument


class AlertCondition(StrEnum):
    ABOVE = "above"  # notify when price >= target
    BELOW = "below"  # notify when price <= target


class AlertStatus(StrEnum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("condition IN ('above', 'below')", name="condition_valid"),
        CheckConstraint("status IN ('active', 'triggered', 'cancelled')", name="status_valid"),
        CheckConstraint("target_price > 0", name="target_positive"),
        # The alert engine's lookup: only active alerts, ordered by price.
        Index(
            "ix_alerts_active_lookup",
            "instrument_id",
            "condition",
            "target_price",
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_alerts_user_status", "user_id", "status"),
        Index("ix_alerts_group_id", "group_id", postgresql_where=text("group_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    condition: Mapped[str] = mapped_column(String(8), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Price when the alert was created or re-armed (for context in the UI).
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=AlertStatus.ACTIVE, server_default="active"
    )
    note: Mapped[str | None] = mapped_column(String(200))
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # A "High & low" alert is two rows (above + below) sharing a group_id.
    group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # When true, the first alert of the group to trigger stops the others.
    one_cancels_other: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    instrument: Mapped[Instrument] = relationship(lazy="joined")
