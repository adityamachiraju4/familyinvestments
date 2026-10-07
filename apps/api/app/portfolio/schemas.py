"""Decimal-based dashboard responses."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from app.models import Bucket


class PortfolioSummary(BaseModel):
    holdings_invested_value: Decimal
    holdings_market_value: Decimal
    available_cash: Decimal
    total_account_value: Decimal
    total_pnl: Decimal
    total_pnl_percent: Decimal
    holding_count: int
    allocation: dict[Bucket, Decimal]
    last_sync_at: datetime | None


class SnapshotView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    snapshot_date: date
    available_cash: Decimal
    holdings_invested_value: Decimal
    holdings_market_value: Decimal
    total_account_value: Decimal
    total_pnl: Decimal
    total_pnl_percent: Decimal
    nifty_value: Decimal
    midcap_value: Decimal
    smallcap_value: Decimal
    other_value: Decimal
    unclassified_value: Decimal | None


class HoldingHistoryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    snapshot_date: date
    tradingsymbol: str
    exchange: str
    bucket: Bucket
    quantity: int
    average_price: Decimal
    last_price: Decimal
    invested_value: Decimal
    market_value: Decimal
    pnl: Decimal
    pnl_percent: Decimal


class MonthlyTargetView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    month: date
    total_target: Decimal
    nifty_target: Decimal
    midcap_target: Decimal
    smallcap_target: Decimal
