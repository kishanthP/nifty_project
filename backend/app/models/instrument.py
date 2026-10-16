from sqlalchemy import Boolean, SmallInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Instrument(TimestampMixin, Base):
    """Something we track prices for (an index or a stock).

    Adding BANKNIFTY or a stock later only needs a new row here — no code change.
    """

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(10), nullable=False)  # INDEX | EQUITY
    # Angel One identifiers: exchange type 1 = NSE cash market, token from their scrip master.
    angelone_exchange_type: Mapped[int | None] = mapped_column(SmallInteger)
    angelone_token: Mapped[str | None] = mapped_column(String(32))
    yahoo_symbol: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)
