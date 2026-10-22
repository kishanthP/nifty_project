import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.models import AlertCondition

# Prices are exact Decimals inside the app and plain numbers in JSON.
Price = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class AlertCreate(BaseModel):
    symbol: str = Field(default="NIFTY50", max_length=32)
    target_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # Leave empty to decide automatically from the current price.
    condition: AlertCondition | None = None
    note: str | None = Field(default=None, max_length=200)


class AlertRangeCreate(BaseModel):
    """'High & low': notify when the price goes above `high_price` or below `low_price`."""

    symbol: str = Field(default="NIFTY50", max_length=32)
    high_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    low_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # True: when one side is hit, the other alert is stopped (only the first breakout).
    one_cancels_other: bool = False
    note: str | None = Field(default=None, max_length=200)


MAX_BATCH_ALERTS = 10


class AlertBatchItem(BaseModel):
    target_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # Leave empty to decide automatically from the current price.
    condition: AlertCondition | None = None


class AlertBatchCreate(BaseModel):
    """'Multiple': several independent alerts (e.g. above 22,310 and above 22,320) at once."""

    symbol: str = Field(default="NIFTY50", max_length=32)
    items: list[AlertBatchItem] = Field(min_length=1, max_length=MAX_BATCH_ALERTS)
    note: str | None = Field(default=None, max_length=200)


class AlertUpdate(BaseModel):
    target_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    condition: AlertCondition | None = None
    note: str | None = Field(default=None, max_length=200)
    # "active" re-arms a triggered alert; "cancelled" pauses it.
    status: Literal["active", "cancelled"] | None = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    instrument_name: str
    condition: AlertCondition
    target_price: Price
    base_price: Price | None
    status: str
    note: str | None
    triggered_at: datetime | None
    triggered_price: Price | None
    group_id: uuid.UUID | None
    one_cancels_other: bool
    created_at: datetime
    updated_at: datetime
