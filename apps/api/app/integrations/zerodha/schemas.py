"""Explicit provider inputs and dashboard outputs; no raw response passthrough."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt
from app.models import Bucket


class ProviderSession(BaseModel):
    user_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    access_token: SecretStr


class ProviderHolding(BaseModel):
    exchange: str = Field(min_length=1, max_length=16)
    tradingsymbol: str = Field(min_length=1, max_length=128)
    instrument_token: StrictInt = Field(ge=0, le=2**63-1)
    quantity: StrictInt = Field(ge=0, le=2**31-1)
    t1_quantity: StrictInt = Field(ge=0, le=2**31-1)
    average_price: Decimal = Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
    last_price: Decimal = Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=8)


class Funds(BaseModel):
    available_cash: Decimal = Field(allow_inf_nan=False)
    opening_balance: Decimal | None = Field(default=None, allow_inf_nan=False)
    live_balance: Decimal | None = Field(default=None, allow_inf_nan=False)
    net: Decimal | None = Field(default=None, allow_inf_nan=False)


class HoldingView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tradingsymbol: str
    exchange: str
    quantity: int
    average_price: Decimal
    last_price: Decimal
    invested_value: Decimal
    current_value: Decimal
    unrealised_pnl: Decimal
    unrealised_pnl_percent: Decimal
    bucket: Bucket
    synced_at: datetime


class ConnectionStatus(BaseModel):
    connection_status: str
    last_authenticated_at: datetime | None
    last_sync_at: datetime | None
    credentials_present: bool
