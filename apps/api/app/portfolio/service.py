"""Portfolio arithmetic and atomic daily snapshot persistence."""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.integrations.zerodha import service as zerodha
from app.integrations.zerodha.schemas import Funds
from app.integrations.zerodha.exceptions import IntegrationError, credentials_error
from app.models import Bucket, Holding, HoldingSnapshot, MonthlyTarget, PortfolioSnapshot, ZerodhaAccount
from app.portfolio.schemas import PortfolioSummary


def today() -> date:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def current_holdings(db: Session, account_id: int) -> list[Holding]:
    return list(db.scalars(select(Holding).where(Holding.account_id == account_id, Holding.is_active.is_(True)).order_by(Holding.exchange, Holding.tradingsymbol)))


def calculate_summary(rows: list[Holding], available_cash: Decimal, last_sync_at: datetime | None) -> PortfolioSummary:
    invested = sum((row.invested_value for row in rows), Decimal(0))
    market = sum((row.current_value for row in rows), Decimal(0))
    pnl = market - invested
    percent = pnl / invested * 100 if invested > 0 else Decimal(0)
    allocation = {bucket: Decimal(0) for bucket in Bucket}
    for row in rows:
        allocation[Bucket(row.bucket)] += row.current_value
    return PortfolioSummary(
        holdings_invested_value=invested, holdings_market_value=market,
        available_cash=available_cash, total_account_value=market + available_cash,
        total_pnl=pnl, total_pnl_percent=percent.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        holding_count=len(rows), allocation=allocation, last_sync_at=last_sync_at,
    )


def summary(db: Session) -> PortfolioSummary:
    account = zerodha.single_account(db)
    funds = zerodha.funds(db)
    return calculate_summary(current_holdings(db, account.id), funds.available_cash, account.last_sync_at)


def snapshot_today(db: Session, *, current_funds: Funds | None = None, commit: bool = True) -> PortfolioSnapshot:
    """One atomic account/day snapshot; repeated writes preserve row identity."""
    try:
        account = zerodha.single_account(db)
        # Serialize snapshots for this account and retain coherent sync metadata.
        account = db.scalars(select(ZerodhaAccount).where(
            ZerodhaAccount.id == account.id,
        ).with_for_update().execution_options(populate_existing=True)).one()
        if account.connection_status != "connected":
            raise credentials_error()
        funds = current_funds if current_funds is not None else zerodha.funds(db)
        rows = current_holdings(db, account.id)
        day = today()
        values = calculate_summary(rows, funds.available_cash, account.last_sync_at)
        data = {
            "account_id": account.id, "snapshot_date": day,
            "available_cash": values.available_cash,
            "holdings_invested_value": values.holdings_invested_value,
            "holdings_market_value": values.holdings_market_value,
            "portfolio_value": values.holdings_market_value,
            "total_account_value": values.total_account_value,
            "day_pnl": Decimal(0),  # Unknown; never equate daily P&L with lifetime P&L.
            "total_pnl": values.total_pnl, "total_pnl_percent": values.total_pnl_percent,
            "unclassified_value": values.allocation[Bucket.UNCLASSIFIED],
            "nifty_value": values.allocation[Bucket.NIFTY_50],
            "midcap_value": values.allocation[Bucket.MID_CAP],
            "smallcap_value": values.allocation[Bucket.SMALL_CAP],
            # Existing schema has no largecap_value column; retain it in residual.
            "other_value": values.allocation[Bucket.OTHER] + values.allocation[Bucket.LARGE_CAP],
        }
        stmt = insert(PortfolioSnapshot).values(**data)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[PortfolioSnapshot.account_id, PortfolioSnapshot.snapshot_date],
            set_={k: v for k, v in data.items() if k not in {"account_id", "snapshot_date"}},
        ))
        # Replacing today's membership is deliberate; older dates stay untouched.
        obsolete = delete(HoldingSnapshot).where(
            HoldingSnapshot.account_id == account.id, HoldingSnapshot.snapshot_date == day,
        )
        keys = [(row.exchange, row.tradingsymbol) for row in rows]
        if keys:
            obsolete = obsolete.where(tuple_(HoldingSnapshot.exchange, HoldingSnapshot.tradingsymbol).not_in(keys))
        db.execute(obsolete)
        for row in rows:
            item = {
                "account_id": account.id, "snapshot_date": day,
                "exchange": row.exchange, "tradingsymbol": row.tradingsymbol,
                "bucket": row.bucket, "quantity": row.quantity,
                "average_price": row.average_price, "last_price": row.last_price,
                "invested_value": row.invested_value, "market_value": row.current_value,
                "pnl": row.unrealised_pnl, "pnl_percent": row.unrealised_pnl_percent,
            }
            stmt = insert(HoldingSnapshot).values(**item)
            db.execute(stmt.on_conflict_do_update(
                index_elements=[HoldingSnapshot.account_id, HoldingSnapshot.snapshot_date, HoldingSnapshot.exchange, HoldingSnapshot.tradingsymbol],
                set_={k: v for k, v in item.items() if k not in {"account_id", "snapshot_date", "exchange", "tradingsymbol"}},
            ))
        snapshot = db.scalars(select(PortfolioSnapshot).where(
            PortfolioSnapshot.account_id == account.id, PortfolioSnapshot.snapshot_date == day,
        ).execution_options(populate_existing=True)).one()
        if commit:
            db.commit()
        return snapshot
    except SQLAlchemyError:
        db.rollback()
        raise IntegrationError("database_unavailable", "Snapshot operation failed") from None
    except IntegrationError:
        db.rollback()
        raise


def snapshot_history(db: Session, limit: int) -> list[PortfolioSnapshot]:
    account = zerodha.single_account(db)
    rows = list(db.scalars(select(PortfolioSnapshot).where(
        PortfolioSnapshot.account_id == account.id,
    ).order_by(PortfolioSnapshot.snapshot_date.desc()).limit(limit)))
    return rows[::-1]


def holding_history(db: Session, symbol: str, limit: int) -> list[HoldingSnapshot]:
    account = zerodha.single_account(db)
    rows = list(db.scalars(select(HoldingSnapshot).where(
        HoldingSnapshot.account_id == account.id, HoldingSnapshot.tradingsymbol == symbol,
    ).order_by(HoldingSnapshot.snapshot_date.desc(), HoldingSnapshot.exchange.desc()).limit(limit)))
    return rows[::-1]


def monthly_target(db: Session, month: date) -> MonthlyTarget:
    account = zerodha.single_account(db)
    target = db.scalar(select(MonthlyTarget).where(
        MonthlyTarget.account_id == account.id, MonthlyTarget.month == month.replace(day=1),
    ))
    if target is None:
        raise IntegrationError("target_missing", "No monthly target configured for this month", 404)
    return target
