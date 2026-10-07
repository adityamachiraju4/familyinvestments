"""Read-only endpoints and one-time correlation-authorized login callback."""

from collections.abc import Generator
from datetime import datetime, timezone
import logging
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.service import require_access
from app import database
from app.config import settings
from app.integrations.zerodha.client import login_url, require_config
from app.integrations.zerodha import login_state
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.schemas import ConnectionStatus, Funds, HoldingView
from app.integrations.zerodha import service
from app.models import Holding

router = APIRouter()
callback_router = APIRouter()
logger = logging.getLogger(__name__)


class CallbackLogFilter(logging.Filter):
    """Uvicorn access logs must not persist callback request tokens."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if str(args[2]).split("?", 1)[0] == "/integrations/zerodha/callback":
                args[2] = "/integrations/zerodha/callback"
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(CallbackLogFilter())


def integration_db() -> Generator[Session, None, None]:
    if database.SessionLocal is None:
        raise IntegrationError("database_unavailable", "Database is not configured")
    try:
        with database.SessionLocal() as db:
            yield db
    except SQLAlchemyError:
        raise IntegrationError("database_unavailable", "Database operation failed") from None


def dashboard_url() -> str:
    """Only server configuration controls the callback destination; never a URL parameter."""
    value = settings.DASHBOARD_URL or ("http://127.0.0.1:5173/" if settings.APP_ENV == "development" else "")
    try:
        url = urlsplit(value)
        url.port
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}))):
            raise ValueError
    except ValueError:
        raise IntegrationError("configuration_missing", "Dashboard return URL is not configured") from None
    return value


@router.get("/integrations/zerodha/login")
def login(response: Response, return_to_dashboard: bool = False, session=Depends(require_access), db: Session = Depends(integration_db)) -> dict[str, str]:
    require_config()
    dashboard_url()  # Validate server-only destination before creating a correlation.
    try:
        state = login_state.create(db, session)
    except login_state.StateRejected:
        db.rollback()
        raise IntegrationError("dashboard_auth_required", "Dashboard login required", 401) from None
    response.headers["Cache-Control"] = "no-store"
    return {"login_url": login_url(state)}


def callback_redirect(result: str):
    response = RedirectResponse(dashboard_url() + "?zerodha=" + result, status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@callback_router.get("/integrations/zerodha/callback")
def callback(request: Request, db: Session = Depends(integration_db)):
    # Authorization is the one-time DB correlation, not a possibly partitioned cookie.
    try:
        require_config()
        dashboard_url()
        params = request.query_params
        token = params.get("request_token", "")
        state = params.get("state", "")
        if (not re.fullmatch(r"[A-Za-z0-9]{1,512}", token)
                or not re.fullmatch(r"[a-f0-9]{64}", state)
                or any(len(params.getlist(key)) != 1 for key in ("request_token", "state"))
                or any(len(params.getlist(key)) > 1 for key in ("status", "action"))
                or params.get("status", "success") != "success"
                or params.get("action", "login") != "login"):
            raise login_state.StateRejected("parameters_invalid")
        configured = urlsplit(settings.ZERODHA_REDIRECT_URL)
        actual = urlsplit(str(request.url))
        if (actual.scheme, actual.netloc, actual.path) != (configured.scheme, configured.netloc, configured.path):
            raise login_state.StateRejected("callback_url_invalid")
        login_state.claim(db, state)
        service.lock_account(db)  # Serialize account binding across different login flows.
        service.connect(db, token)  # Existing exchange, account binding, encryption and commit.
        return callback_redirect("connected")
    except login_state.StateRejected as exc:
        db.rollback()
        logger.warning("zerodha_callback_failed reason=%s", str(exc))
    except IntegrationError:
        db.rollback()
        logger.warning("zerodha_callback_failed reason=exchange_or_configuration_failed")
    except Exception:
        db.rollback()
        logger.warning("zerodha_callback_failed reason=internal_failure")
    return callback_redirect("connect_failed")


@router.get("/integrations/zerodha/status", response_model=ConnectionStatus)
def status(db: Session = Depends(integration_db)) -> ConnectionStatus:
    account = service.single_account(db)
    from app.portfolio.activity import refresh_required
    stored = service.credential(db, account)
    expires = stored.token_expires_at if stored else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    valid = bool(stored and expires > datetime.now(timezone.utc) and account.connection_status == "connected")
    return ConnectionStatus(
        connection_status=("expired" if stored and not valid else account.connection_status),
        last_authenticated_at=account.last_authenticated_at, last_sync_at=account.last_sync_at,
        credentials_present=stored is not None,
        token_valid=valid, refresh_required=refresh_required(account.last_refresh_at),
        last_refresh_at=account.last_refresh_at,
    )


@router.get("/portfolio/funds", response_model=Funds)
def funds(db: Session = Depends(integration_db)) -> Funds:
    return service.funds(db)


@router.post("/integrations/zerodha/sync/holdings")
def sync(db: Session = Depends(integration_db)) -> dict:
    return {"status": "ok", "holdings_synced": service.sync_holdings(db)}


@router.get("/portfolio/holdings", response_model=list[HoldingView])
def holdings(db: Session = Depends(integration_db)) -> list[HoldingView]:
    account = service.single_account(db)
    rows = db.scalars(select(Holding).where(Holding.account_id == account.id, Holding.is_active.is_(True)).order_by(Holding.exchange, Holding.tradingsymbol)).all()
    return [HoldingView.model_validate(row).model_copy(update={"bucket": service.classify_instrument(row.tradingsymbol, row.exchange, row.instrument_token)}) for row in rows]
