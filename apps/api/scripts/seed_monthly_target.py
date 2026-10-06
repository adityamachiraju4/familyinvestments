"""Idempotently seed the agreed October 2026 development target."""

from datetime import date
from decimal import Decimal
import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import database
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.service import single_account
from app.models import MonthlyTarget
from app.portfolio.schemas import MonthlyTargetView


def seed_target(db: Session) -> MonthlyTarget:
    account = single_account(db)
    values = {
        "account_id": account.id, "month": date(2026, 10, 1),
        "total_target": Decimal("15000"), "nifty_target": Decimal("8000"),
        "midcap_target": Decimal("5000"), "smallcap_target": Decimal("2000"),
    }
    stmt = insert(MonthlyTarget).values(**values)
    db.execute(stmt.on_conflict_do_update(
        index_elements=[MonthlyTarget.account_id, MonthlyTarget.month],
        set_={**{k: v for k, v in values.items() if k not in {"account_id", "month"}}, "updated_at": stmt.excluded.updated_at},
    ))
    return db.scalars(select(MonthlyTarget).where(
        MonthlyTarget.account_id == account.id, MonthlyTarget.month == values["month"],
    ).execution_options(populate_existing=True)).one()


def main() -> None:
    if database.SessionLocal is None:
        raise SystemExit("DATABASE_URL must be configured before seeding")
    try:
        with database.SessionLocal.begin() as db:
            target = seed_target(db)
            result = MonthlyTargetView.model_validate(target).model_dump(mode="json")
    except (SQLAlchemyError, IntegrationError):
        raise SystemExit("Monthly target seed failed; check database and account configuration") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
