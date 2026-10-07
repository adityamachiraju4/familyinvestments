"""Household mutual funds, independent of brokerage credentials and instruments."""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from sqlalchemy import String, ForeignKey, Numeric, UniqueConstraint, CheckConstraint, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.common import MONEY, Timestamps, CreatedAt

class Source(StrEnum):
    GROWW = 'GROWW'
    CAS = 'CAS'
    MANUAL = 'MANUAL'

class Category(StrEnum):
    NIFTY_50 = 'NIFTY_50'
    LARGE_CAP = 'LARGE_CAP'
    MID_CAP = 'MID_CAP'
    SMALL_CAP = 'SMALL_CAP'
    FLEXI_CAP = 'FLEXI_CAP'
    MULTI_CAP = 'MULTI_CAP'
    HYBRID = 'HYBRID'
    DEBT = 'DEBT'
    GOLD = 'GOLD'
    INTERNATIONAL = 'INTERNATIONAL'
    OTHER = 'OTHER'
    UNCLASSIFIED = 'UNCLASSIFIED'

def enum(kind, name):
    return Enum(kind, name=name, native_enum=False, create_constraint=True, validate_strings=True)

class MutualFundAccount(Timestamps, Base):
    __tablename__ = 'mutual_fund_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))

class MutualFundScheme(Timestamps, Base):
    __tablename__ = 'mutual_fund_schemes'
    __table_args__ = (UniqueConstraint('account_id', 'scheme_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('mutual_fund_accounts.id'))
    scheme_key: Mapped[str] = mapped_column(String(255))
    scheme_name: Mapped[str] = mapped_column(String(255))
    isin: Mapped[str | None] = mapped_column(String(32))
    folio_number: Mapped[str | None] = mapped_column(String(128))
    plan_type: Mapped[str | None] = mapped_column(String(64))
    option_type: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[Category] = mapped_column(enum(Category, 'mf_category'), default=Category.UNCLASSIFIED)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    history_complete: Mapped[bool] = mapped_column(default=False)

class SIP(Timestamps, Base):
    __tablename__ = 'sips'
    __table_args__ = (CheckConstraint('monthly_amount > 0', name='positive_amount'), CheckConstraint('sip_day IS NULL OR (sip_day >= 1 AND sip_day <= 31)', name='valid_day'), CheckConstraint("status IN ('ACTIVE','PAUSED','STOPPED')", name='valid_status'), CheckConstraint('end_date IS NULL OR end_date >= start_date', name='valid_dates'))
    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey('mutual_fund_schemes.id'))
    source: Mapped[Source] = mapped_column(enum(Source, 'sip_source'))
    monthly_amount: Mapped[Decimal] = mapped_column(MONEY)
    sip_day: Mapped[int | None]
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    status: Mapped[str] = mapped_column(String(16))

class MutualFundTransaction(CreatedAt, Base):
    __tablename__ = 'mutual_fund_transactions'
    __table_args__ = (UniqueConstraint('scheme_id','source','import_key'), CheckConstraint('amount > 0', name='positive_amount'), CheckConstraint("transaction_type IN ('PURCHASE','SIP','REDEMPTION','SWITCH_IN','SWITCH_OUT','DIVIDEND')", name='valid_type'), CheckConstraint("status IN ('CONFIRMED','PENDING','CANCELLED')", name='valid_status'))
    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey('mutual_fund_schemes.id'))
    sip_id: Mapped[int | None] = mapped_column(ForeignKey('sips.id'))
    source: Mapped[Source] = mapped_column(enum(Source, 'mf_transaction_source'))
    import_key: Mapped[str] = mapped_column(String(255))
    transaction_date: Mapped[date]
    transaction_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    units: Mapped[Decimal | None] = mapped_column(Numeric(24,8))
    nav: Mapped[Decimal | None] = mapped_column(Numeric(24,8))
    status: Mapped[str] = mapped_column(String(16), default='CONFIRMED')

class MutualFundHolding(Timestamps, Base):
    __tablename__ = 'mutual_fund_holdings'
    __table_args__ = (CheckConstraint('current_value >= 0', name='nonnegative_value'),)
    scheme_id: Mapped[int] = mapped_column(ForeignKey('mutual_fund_schemes.id'), primary_key=True)
    source: Mapped[Source] = mapped_column(enum(Source, 'mf_holding_source'))
    units: Mapped[Decimal | None] = mapped_column(Numeric(24,8))
    invested_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    latest_nav: Mapped[Decimal | None] = mapped_column(Numeric(24,8))
    current_value: Mapped[Decimal] = mapped_column(MONEY)
    valuation_date: Mapped[date]
