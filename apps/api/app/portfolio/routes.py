"""Read-only portfolio views and explicit local snapshot creation."""

from datetime import date
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.routes import integration_db
from app.portfolio import service
from app.portfolio.activity_schemas import RefreshResult, ActivityView, ContributionsView
from app.portfolio.schemas import HoldingHistoryView, MonthlyTargetView, PortfolioSummary, SnapshotView

router = APIRouter(prefix="/portfolio")


@router.get("/summary", response_model=PortfolioSummary)
def summary(db: Session = Depends(integration_db)) -> PortfolioSummary:
    return service.summary(db)


@router.post("/snapshots/today", response_model=SnapshotView)
def snapshot_today(db: Session = Depends(integration_db)):
    return service.snapshot_today(db)


@router.get("/snapshots", response_model=list[SnapshotView])
def snapshots(limit: int = Query(default=30, ge=1, le=3650), db: Session = Depends(integration_db)):
    """Return the newest N daily snapshots in chronological ascending order."""
    return service.snapshot_history(db, limit)


@router.get("/holdings/{tradingsymbol}/history", response_model=list[HoldingHistoryView])
def holding_history(tradingsymbol: str, limit: int = Query(default=30, ge=1, le=3650), db: Session = Depends(integration_db)):
    """Newest N symbol rows ascending by date then exchange; exchanges remain distinct."""
    return service.holding_history(db, tradingsymbol, limit)


@router.get("/monthly-target", response_model=MonthlyTargetView)
def monthly_target(month: str | None = None, db: Session = Depends(integration_db)):
    if month is None:
        selected = service.today().replace(day=1)
    else:
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month):
                raise ValueError
            selected = date.fromisoformat(month + "-01")
        except ValueError:
            raise IntegrationError("month_invalid", "Month must use YYYY-MM format", 422) from None
    return service.monthly_target(db, selected)


@router.post("/refresh", response_model=RefreshResult)
def refresh(if_stale: bool = False, db: Session = Depends(integration_db)):
    from app.portfolio.activity import refresh_portfolio
    return refresh_portfolio(db, if_stale=if_stale)


@router.get("/activity/today", response_model=ActivityView)
def activity_today(db: Session = Depends(integration_db)):
    from app.portfolio.activity import today_activity
    return today_activity(db)


@router.get("/contributions/month", response_model=ContributionsView)
def contributions_month(db: Session = Depends(integration_db)):
    from app.portfolio.activity import contributions
    return contributions(db)
