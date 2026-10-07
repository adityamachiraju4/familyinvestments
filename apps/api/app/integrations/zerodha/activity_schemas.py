"""Validated current-day provider books; explicit fill identity and India time."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

INDIA = ZoneInfo("Asia/Kolkata")
Amount = Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=8)


class ProviderOrder(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    tradingsymbol: str = Field(min_length=1, max_length=128)
    exchange: str = Field(min_length=1, max_length=16)
    transaction_type: Literal["BUY", "SELL"]
    product: str = Field(min_length=1, max_length=32)
    order_type: str = Field(min_length=1, max_length=32)
    quantity: StrictInt = Field(ge=1, le=2**31-1)
    filled_quantity: StrictInt = Field(ge=0, le=2**31-1)
    price: Decimal = Amount
    average_price: Decimal = Amount
    status: str = Field(min_length=1, max_length=32)
    order_timestamp: datetime
    exchange_timestamp: datetime | None = None

    @field_validator("order_timestamp", "exchange_timestamp")
    @classmethod
    def local_time(cls, value):
        if value is None:
            return None
        return value.replace(tzinfo=INDIA) if value.tzinfo is None else value.astimezone(INDIA)

    @model_validator(mode="after")
    def filled_within_quantity(self):
        if self.filled_quantity > self.quantity:
            raise ValueError("Filled quantity exceeds order quantity")
        return self


class ProviderTrade(BaseModel):
    trade_id: str = Field(min_length=1, max_length=64)
    order_id: str = Field(min_length=1, max_length=64)
    tradingsymbol: str = Field(min_length=1, max_length=128)
    exchange: str = Field(min_length=1, max_length=16)
    instrument_token: StrictInt | None = Field(default=None, ge=0, le=2**63-1)
    product: str = Field(min_length=1, max_length=32)
    transaction_type: Literal["BUY", "SELL"]
    quantity: StrictInt = Field(ge=1, le=2**31-1)
    average_price: Decimal = Amount
    fill_timestamp: datetime

    @field_validator("fill_timestamp")
    @classmethod
    def local_time(cls, value):
        return value.replace(tzinfo=INDIA) if value.tzinfo is None else value.astimezone(INDIA)
