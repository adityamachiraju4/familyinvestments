"""Frontend-facing executions, order context and refresh state."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel
from app.models import Bucket
from app.portfolio.schemas import PortfolioSummary


class ExecutionView(BaseModel):
    symbol: str
    exchange: str
    transaction_type: str
    product: str
    quantity: int
    average_price: Decimal
    amount: Decimal
    bucket: Bucket
    executed_at: datetime
    order_id: str
    fill_count: int
    charges: Decimal | None = None
    holding_status: Literal["AWAITING_HOLDINGS", "HOLDING_PRESENT_UNCONFIRMED", "NETTED_BY_SELLS", "NOT_APPLICABLE"]


class OrderActivityView(BaseModel):
    symbol: str
    exchange: str
    transaction_type: str
    product: str
    quantity: int
    filled_quantity: int
    status: str
    average_price: Decimal
    timestamp: datetime
    order_id: str


class ActivityView(BaseModel):
    date: date
    last_synced_at: datetime | None
    executed: list[ExecutionView]
    orders: list[OrderActivityView]
    awaiting_holdings: list[ExecutionView]
    open_pending_count: int
    rejected_cancelled_count: int


class ContributionsView(BaseModel):
    month: date
    recorded_from: date | None
    recorded_buy_amount: Decimal
    allocation: dict[Bucket, Decimal]
    history_complete: bool = False
    charges: Decimal | None = None


class RefreshResult(BaseModel):
    status: Literal["ok", "fresh", "reconnect_required"]
    last_refresh_at: datetime | None = None
    holdings_synced: int = 0
    orders_synced: int = 0
    trades_synced: int = 0
    summary: PortfolioSummary | None = None
