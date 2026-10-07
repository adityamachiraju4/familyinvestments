"""Single-account authentication persistence and read-only holdings synchronization."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select, tuple_, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.zerodha.buckets import classify_instrument
from app.integrations.zerodha.client import KiteClient, require_config
from app.integrations.zerodha.crypto import decrypt_token, encrypt_token
from app.integrations.zerodha.exceptions import IntegrationError, credentials_error, provider_error
from app.integrations.zerodha.schemas import Funds, ProviderHolding, ProviderSession
from app.models import Bucket, Holding, ZerodhaAccount, ZerodhaCredential

def single_account(db: Session) -> ZerodhaAccount:
    accounts = db.scalars(select(ZerodhaAccount).limit(2)).all()
    if len(accounts) != 1:
        raise IntegrationError("account_configuration", "Exactly one brokerage account must be configured", 409)
    return accounts[0]


def credential(db: Session, account: ZerodhaAccount) -> ZerodhaCredential | None:
    return db.scalar(select(ZerodhaCredential).where(ZerodhaCredential.account_id == account.id))


def authenticated_client(db: Session, account: ZerodhaAccount) -> KiteClient:
    require_config()
    stored = credential(db, account)
    if stored is None:
        raise credentials_error()
    expires = stored.token_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise credentials_error()
    return KiteClient(decrypt_token(stored.encrypted_access_token))


def connect(db: Session, request_token: str) -> None:
    account = single_account(db)
    try:
        session = ProviderSession.model_validate(KiteClient().exchange_token(request_token))
    except ValidationError:
        raise provider_error() from None
    if account.client_id not in {"LOCAL_DEV", session.user_id}:
        raise IntegrationError("account_mismatch", "Authenticated brokerage account does not match the configured account", 409)
    token = session.access_token.get_secret_value()
    # Validate token syntax before persistence, as it becomes an HTTP header.
    KiteClient(token)
    now = datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    expires = datetime.combine(local.date() + timedelta(days=1), time(6), ZoneInfo("Asia/Kolkata"))
    encrypted = encrypt_token(token)
    stmt = insert(ZerodhaCredential).values(
        account_id=account.id, encrypted_access_token=encrypted,
        token_created_at=now, token_expires_at=expires,
    )
    db.execute(stmt.on_conflict_do_update(index_elements=[ZerodhaCredential.account_id], set_={
        "encrypted_access_token": encrypted, "token_created_at": now,
        "token_expires_at": expires, "updated_at": now,
    }))
    account.client_id = session.user_id
    account.connection_status = "connected"
    account.last_authenticated_at = now
    account.last_refresh_at = None
    db.commit()


def normalize_funds(payload: dict) -> Funds:
    """Prefer current live equity balance, then net, then raw cash as last resort."""
    try:
        if not isinstance(payload, dict):
            raise provider_error()
        available = payload.get("available", {})
        if not isinstance(available, dict):
            raise provider_error()
        live = available.get("live_balance")
        net = payload.get("net")
        current = live if live is not None else net
        if current is None:
            current = available.get("cash")
        if current is None:
            raise provider_error()
        return Funds(
            available_cash=current, opening_balance=available.get("opening_balance"),
            live_balance=live, net=net,
        )
    except (TypeError, AttributeError, ValidationError):
        raise provider_error() from None


def funds(db: Session) -> Funds:
    account = single_account(db)
    return normalize_funds(authenticated_client(db, account).get_margins())


def normalize_holding(payload: dict, account_id: int, synced_at: datetime) -> dict:
    try:
        holding = ProviderHolding.model_validate(payload)
        invested = holding.quantity * holding.average_price
        current = holding.quantity * holding.last_price
        pnl = current - invested
        percent = pnl / invested * 100 if invested else Decimal(0)
        values = {
            "average_price": holding.average_price, "last_price": holding.last_price,
            "invested_value": invested, "current_value": current, "unrealised_pnl": pnl,
        }
        values = {k: v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) for k, v in values.items()}
        percent = percent.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if any(abs(v) >= Decimal("1e16") for v in values.values()) or abs(percent) >= Decimal("1e6"):
            raise provider_error()
        return {
            **values, "account_id": account_id, "exchange": holding.exchange,
            "tradingsymbol": holding.tradingsymbol, "instrument_token": holding.instrument_token,
            "quantity": holding.quantity, "t1_quantity": holding.t1_quantity,
            "unrealised_pnl_percent": percent,
            "bucket": classify_instrument(holding.tradingsymbol, holding.exchange, holding.instrument_token), "synced_at": synced_at,
        }
    except (ValidationError, InvalidOperation):
        raise provider_error() from None


def validated_holdings(payload, account_id: int, now: datetime) -> list[dict]:
    if not isinstance(payload, list):
        raise provider_error()
    rows = [normalize_holding(row, account_id, now) for row in payload]
    if len({(row["exchange"], row["tradingsymbol"]) for row in rows}) != len(rows):
        raise provider_error()
    return rows


def persist_holdings(db: Session, account: ZerodhaAccount, rows: list[dict], now: datetime) -> None:
    """Caller holds the account lock and owns commit/rollback."""
    keys = [(row["exchange"], row["tradingsymbol"]) for row in rows]
    for row in rows:
        row = {**row, "is_active": True}
        stmt = insert(Holding).values(**row)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[Holding.account_id, Holding.exchange, Holding.tradingsymbol],
            set_={key: value for key, value in row.items() if key not in {"account_id", "exchange", "tradingsymbol"}},
        ))
    stale = update(Holding).where(Holding.account_id == account.id)
    if keys:
        stale = stale.where(tuple_(Holding.exchange, Holding.tradingsymbol).not_in(keys))
    db.execute(stale.values(is_active=False).execution_options(synchronize_session=False))
    account.last_sync_at = now
    db.flush()
    db.expire_all()


def lock_account(db: Session) -> ZerodhaAccount:
    account = single_account(db)
    return db.scalars(select(ZerodhaAccount).where(
        ZerodhaAccount.id == account.id,
    ).with_for_update().execution_options(populate_existing=True)).one()


def sync_holdings(db: Session) -> int:
    """Validate and reconcile the complete provider list, without physical deletion."""
    try:
        account = lock_account(db)
        payload = authenticated_client(db, account).get_holdings()
        now = datetime.now(timezone.utc)
        rows = validated_holdings(payload, account.id, now)
        persist_holdings(db, account, rows, now)
        db.commit()
        return len(rows)
    except SQLAlchemyError:
        db.rollback()
        raise IntegrationError("database_unavailable", "Holdings sync operation failed") from None
    except Exception:
        db.rollback()
        raise
