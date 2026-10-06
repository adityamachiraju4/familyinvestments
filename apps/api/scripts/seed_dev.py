"""Seed safe account metadata with: python -m scripts.seed_dev."""

import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import database
from app.models import ZerodhaAccount


def seed_account(session: Session) -> ZerodhaAccount:
    """Create the placeholder once, preserving any existing account metadata."""
    session.execute(
        insert(ZerodhaAccount)
        .values(
            client_id="LOCAL_DEV",
            display_name="Primary Zerodha Account",
            connection_status="disconnected",
        )
        .on_conflict_do_nothing(index_elements=[ZerodhaAccount.client_id])
    )
    return session.scalars(
        select(ZerodhaAccount).where(ZerodhaAccount.client_id == "LOCAL_DEV")
    ).one()


def main() -> None:
    if database.SessionLocal is None:
        raise SystemExit("DATABASE_URL must be configured before seeding")
    try:
        with database.SessionLocal.begin() as session:
            account = seed_account(session)
            result = {
                "id": account.id,
                "client_id": account.client_id,
                "display_name": account.display_name,
                "connection_status": account.connection_status,
            }
    except SQLAlchemyError:
        raise SystemExit("Development seed failed; check database configuration and migration status") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
