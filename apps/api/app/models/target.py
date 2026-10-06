"""Monthly investment target schema."""

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.database import Base
from app.models.common import MONEY, Timestamps


class MonthlyTarget(Timestamps, Base):
    __tablename__ = "monthly_targets"
    __table_args__ = (
        UniqueConstraint("account_id", "month"),
        CheckConstraint("EXTRACT(DAY FROM month) = 1", name="month_first_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("zerodha_accounts.id"))
    month: Mapped[date]
    total_target: Mapped[Decimal] = mapped_column(MONEY)
    nifty_target: Mapped[Decimal] = mapped_column(MONEY)
    midcap_target: Mapped[Decimal] = mapped_column(MONEY)
    smallcap_target: Mapped[Decimal] = mapped_column(MONEY)

    @validates("month")
    def normalize_month(self, key: str, value: date) -> date:
        return value.replace(day=1)
