"""Current holdings and historical portfolio schema."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, true, BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import BUCKET, MONEY, PERCENT, Bucket, CreatedAt


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "exchange", "tradingsymbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    exchange: Mapped[str] = mapped_column(String(16))
    tradingsymbol: Mapped[str] = mapped_column(String(128))
    instrument_token: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int]
    t1_quantity: Mapped[int]
    average_price: Mapped[Decimal] = mapped_column(MONEY)
    last_price: Mapped[Decimal] = mapped_column(MONEY)
    invested_value: Mapped[Decimal] = mapped_column(MONEY)
    current_value: Mapped[Decimal] = mapped_column(MONEY)
    unrealised_pnl: Mapped[Decimal] = mapped_column(MONEY)
    unrealised_pnl_percent: Mapped[Decimal] = mapped_column(PERCENT)
    bucket: Mapped[Bucket] = mapped_column(BUCKET, default=Bucket.UNCLASSIFIED, server_default="UNCLASSIFIED")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)

    @property
    def effective_quantity(self) -> int:
        """Owned delivery units, including receivable T1 units; preserve raw fields."""
        return self.quantity + self.t1_quantity


class PortfolioSnapshot(CreatedAt, Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "snapshot_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    snapshot_date: Mapped[date]
    available_cash: Mapped[Decimal] = mapped_column(MONEY)
    holdings_invested_value: Mapped[Decimal] = mapped_column(MONEY)
    holdings_market_value: Mapped[Decimal] = mapped_column(MONEY)
    portfolio_value: Mapped[Decimal] = mapped_column(MONEY)
    total_account_value: Mapped[Decimal] = mapped_column(MONEY)
    day_pnl: Mapped[Decimal] = mapped_column(MONEY)
    total_pnl: Mapped[Decimal] = mapped_column(MONEY)
    total_pnl_percent: Mapped[Decimal] = mapped_column(PERCENT)
    nifty_value: Mapped[Decimal] = mapped_column(MONEY)
    midcap_value: Mapped[Decimal] = mapped_column(MONEY)
    smallcap_value: Mapped[Decimal] = mapped_column(MONEY)
    other_value: Mapped[Decimal] = mapped_column(MONEY)
    unclassified_value: Mapped[Decimal | None] = mapped_column(MONEY)


class HoldingSnapshot(CreatedAt, Base):
    __tablename__ = "holding_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", "exchange", "tradingsymbol"),
        Index("ix_holding_snapshots_account_date", "account_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    snapshot_date: Mapped[date]
    exchange: Mapped[str] = mapped_column(String(16))
    tradingsymbol: Mapped[str] = mapped_column(String(128))
    bucket: Mapped[Bucket] = mapped_column(BUCKET, default=Bucket.UNCLASSIFIED, server_default="UNCLASSIFIED")
    quantity: Mapped[int]
    average_price: Mapped[Decimal] = mapped_column(MONEY)
    last_price: Mapped[Decimal] = mapped_column(MONEY)
    invested_value: Mapped[Decimal] = mapped_column(MONEY)
    market_value: Mapped[Decimal] = mapped_column(MONEY)
    pnl: Mapped[Decimal] = mapped_column(MONEY)
    pnl_percent: Mapped[Decimal] = mapped_column(PERCENT)
