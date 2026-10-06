"""Order and investment transaction schema; no brokerage API integration."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import BUCKET, MONEY, Bucket, CreatedAt


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("account_id", "zerodha_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    zerodha_order_id: Mapped[str] = mapped_column(String(64))
    tradingsymbol: Mapped[str] = mapped_column(String(128))
    exchange: Mapped[str] = mapped_column(String(16))
    transaction_type: Mapped[str] = mapped_column(String(16))
    product: Mapped[str] = mapped_column(String(32))
    order_type: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int]
    filled_quantity: Mapped[int]
    price: Mapped[Decimal] = mapped_column(MONEY)
    average_price: Mapped[Decimal] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(32))
    order_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exchange_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestmentTransaction(CreatedAt, Base):
    __tablename__ = "investment_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    trade_date: Mapped[date]
    tradingsymbol: Mapped[str] = mapped_column(String(128))
    exchange: Mapped[str] = mapped_column(String(16))
    bucket: Mapped[Bucket] = mapped_column(BUCKET, default=Bucket.OTHER, server_default="OTHER")
    quantity: Mapped[int]
    price: Mapped[Decimal] = mapped_column(MONEY)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY)
    charges: Mapped[Decimal] = mapped_column(MONEY)
    net_amount: Mapped[Decimal] = mapped_column(MONEY)
