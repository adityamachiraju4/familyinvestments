"""One household identity; signed opaque cookies, DB revocation and CSRF."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from collections.abc import Generator
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app import database
from app.config import settings
from app.models.auth import DashboardSession, LoginAttempt
from app.auth.passwords import parse_hash, verify

WINDOW = 900


def validate_config(configuration=settings):
    try:
        if (not configuration.DASHBOARD_USERNAME or len(configuration.DASHBOARD_USERNAME) > 128 or not configuration.DASHBOARD_PASSWORD_HASH
                or not configuration.SESSION_SECRET or len(configuration.SESSION_SECRET.get_secret_value()) < 32
                or not 300 <= configuration.SESSION_TTL_SECONDS <= 86400):
            raise ValueError
        parse_hash(configuration.DASHBOARD_PASSWORD_HASH.get_secret_value())
    except ValueError:
        raise RuntimeError('Dashboard authentication configuration is missing or invalid') from None


def auth_db() -> Generator[Session, None, None]:
    if database.SessionLocal is None:
        raise HTTPException(503, 'Dashboard authentication unavailable')
    try:
        with database.SessionLocal() as db:
            yield db
    except SQLAlchemyError:
        raise HTTPException(503, 'Dashboard authentication unavailable') from None


def sign(value: str) -> str:
    validate_config()
    return hmac.new(settings.SESSION_SECRET.get_secret_value().encode(), value.encode(), hashlib.sha256).hexdigest()


def cookie_name() -> str:
    return 'dashboard_session' if settings.APP_ENV == 'development' else '__Host-dashboard_session'


def cookie_options() -> dict:
    production = settings.APP_ENV != 'development'
    return dict(httponly=True, secure=production, samesite='none' if production else 'lax', path='/')


def credential_version() -> str:
    return sign('credential:' + settings.DASHBOARD_USERNAME + ':' + settings.DASHBOARD_PASSWORD_HASH.get_secret_value())


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def find_session(request: Request, db: Session):
    value = request.cookies.get(cookie_name(), '')
    if len(value) != 129:
        return None
    token, separator, signature = value.partition('.')
    try:
        if not separator or not hmac.compare_digest(sign('session:' + token).encode(), signature.encode()):
            return None
        row = db.scalar(select(DashboardSession).where(DashboardSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        if row and aware(row.expires_at) > now() and hmac.compare_digest(row.credential_version, credential_version()):
            return row
    except RuntimeError:
        return None
    return None


def origin_check(request: Request):
    if request.headers.get('origin') not in settings.cors_origins():
        raise HTTPException(403, 'Request origin is not allowed')


def csrf_token(row):
    return sign('csrf:' + row.token_hash)


def require_access(request: Request, db: Session = Depends(auth_db)):
    row = find_session(request, db)
    if row is None:
        raise HTTPException(401, detail={'error':'dashboard_auth_required', 'message':'Dashboard login required'})
    if request.method not in {'GET','HEAD','OPTIONS'} or request.url.path == '/integrations/zerodha/login':
        origin_check(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token','').encode(), csrf_token(row).encode()):
            raise HTTPException(403, 'Session verification failed')
    return row


def login(db: Session, username: str, password: str, address: str):
    validate_config()
    moment = now()
    # Stable global credential window resists rotating IPs/usernames; keys hide IPs.
    keys = (sign('limit:household'), sign('limit:ip:' + address))
    rows = []
    # Consistent lock order across instances. Check global budget before creating IP keys.
    for key, limit in zip(keys, (30, 10)):
        db.execute(insert(LoginAttempt).values(key_hash=key, window_started_at=moment, attempts=0).on_conflict_do_nothing(index_elements=[LoginAttempt.key_hash]))
        row = db.scalar(select(LoginAttempt).where(LoginAttempt.key_hash == key).with_for_update())
        if aware(row.window_started_at) + timedelta(seconds=WINDOW) <= moment:
            row.window_started_at, row.attempts = moment, 0
        if row.attempts >= limit:
            db.commit()
            raise HTTPException(429, 'Too many login attempts. Try again later.', headers={'Retry-After':str(WINDOW)})
        rows.append(row)
    for row in rows:
        row.attempts += 1
    valid_password = verify(password, settings.DASHBOARD_PASSWORD_HASH.get_secret_value())
    valid_username = hmac.compare_digest(username.encode(), settings.DASHBOARD_USERNAME.encode())
    if not (valid_password and valid_username):
        db.commit()
        raise HTTPException(401, 'Invalid username or password')
    token = secrets.token_hex(32)
    row = DashboardSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), credential_version=credential_version(), expires_at=moment + timedelta(seconds=settings.SESSION_TTL_SECONDS))
    db.add(row)
    # Bound expired session retention. Attempts retain only keyed counters, not events.
    db.execute(delete(DashboardSession).where(DashboardSession.expires_at <= moment).execution_options(synchronize_session=False))
    db.commit()
    return row, token + '.' + sign('session:' + token)
