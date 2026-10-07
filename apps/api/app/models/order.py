"""Order and investment transaction schema; read-only provider books and execution fills."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
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
    book_date: Mapped[date | None]


class InvestmentTransaction(CreatedAt, Base):
    __tablename__ = "investment_transactions"
    __table_args__ = (UniqueConstraint(
        "account_id", "trade_date", "exchange", "zerodha_order_id", "zerodha_trade_id",
        name="uq_investment_transactions_provider_fill",
    ),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    trade_date: Mapped[date]
    tradingsymbol: Mapped[str] = mapped_column(String(128))
    exchange: Mapped[str] = mapped_column(String(16))
    bucket: Mapped[Bucket] = mapped_column(BUCKET, default=Bucket.UNCLASSIFIED, server_default="UNCLASSIFIED")
    quantity: Mapped[int]
    price: Mapped[Decimal] = mapped_column(MONEY)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY)
    charges: Mapped[Decimal | None] = mapped_column(MONEY)
    net_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    # Nullable additions preserve legacy transactions without inventing fill data.
    zerodha_trade_id: Mapped[str | None] = mapped_column(String(64))
    zerodha_order_id: Mapped[str | None] = mapped_column(String(64))
    instrument_token: Mapped[int | None] = mapped_column(BigInteger)
    product: Mapped[str | None] = mapped_column(String(32))
    transaction_type: Mapped[str | None] = mapped_column(String(16))
    fill_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
