"""Shared schema types and timestamp columns."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

MONEY = Numeric(20, 4)
PERCENT = Numeric(12, 6)


class Bucket(StrEnum):
    NIFTY_50 = "NIFTY_50"
    MID_CAP = "MID_CAP"
    SMALL_CAP = "SMALL_CAP"
    LARGE_CAP = "LARGE_CAP"
    OTHER = "OTHER"


BUCKET = Enum(Bucket, name="bucket", native_enum=False, create_constraint=True, validate_strings=True)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
