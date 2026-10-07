"""Local read-only dashboard endpoints and browser-bound login callback."""

from collections.abc import Generator
import hmac
import json
from datetime import datetime, timezone
import logging
import re
import secrets
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
from app.integrations.zerodha.crypto import decrypt_token, encrypt_token
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.schemas import ConnectionStatus, Funds, HoldingView
from app.integrations.zerodha import service
from app.models import Holding

router = APIRouter()
COOKIE = "zerodha_login_state"


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
def login(response: Response, return_to_dashboard: bool = False, session=Depends(require_access)) -> dict[str, str]:
    require_config()
    if return_to_dashboard:
        dashboard_url()  # Validate the configured destination before starting login.
    state = encrypt_token(json.dumps({"nonce": secrets.token_urlsafe(32), "dashboard": return_to_dashboard, "session": session.token_hash}))
    response.set_cookie(
        COOKIE, state, max_age=600, httponly=True, samesite="lax",
        secure=urlsplit(settings.ZERODHA_REDIRECT_URL).scheme == "https",
        path="/integrations/zerodha/callback",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"login_url": login_url(state)}


@router.get("/integrations/zerodha/callback")
def callback(request: Request, response: Response, db: Session = Depends(integration_db), session=Depends(require_access)):
    require_config()
    params = request.query_params
    request_token = params.get("request_token", "")
    state = params.get("state", "")
    cookie = request.cookies.get(COOKIE, "")
    if not request_token or len(request_token) > 512 or not re.fullmatch(r"[A-Za-z0-9]+", request_token):
        raise IntegrationError("callback_invalid", "Invalid Zerodha callback", 400)
    if not state or not cookie or len(state) > 2048 or len(cookie) > 2048 or not hmac.compare_digest(state.encode(), cookie.encode()):
        raise IntegrationError("callback_invalid", "Start Zerodha login in this browser before authenticating", 400)
    try:
        state_data = json.loads(decrypt_token(state, ttl=600))
    except (IntegrationError, ValueError):
        raise IntegrationError("callback_invalid", "Zerodha login has expired; start again", 400) from None
    if not isinstance(state_data, dict) or not hmac.compare_digest(str(state_data.get("session", "")), session.token_hash):
        raise IntegrationError("callback_invalid", "Zerodha login belongs to a different dashboard session", 400)
    configured = urlsplit(settings.ZERODHA_REDIRECT_URL)
    actual = urlsplit(str(request.url))
    if (actual.scheme, actual.netloc, actual.path) != (configured.scheme, configured.netloc, configured.path):
        raise IntegrationError("callback_invalid", "Callback URL does not match the configured redirect URL", 400)
    service.connect(db, request_token)
    if isinstance(state_data, dict) and state_data.get("dashboard") is True:
        response = RedirectResponse(dashboard_url(), status_code=303)
    response.delete_cookie(COOKIE, path="/integrations/zerodha/callback")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response if isinstance(response, RedirectResponse) else {"status": "connected"}


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
    return [HoldingView.model_validate(row) for row in rows]
