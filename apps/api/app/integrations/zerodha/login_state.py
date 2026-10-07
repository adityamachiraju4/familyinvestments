"""Persist opaque correlations and commit one-time claims before external exchange."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from sqlalchemy import select, update
from app.auth import service as auth
from app.models.auth import DashboardSession
from app.models.zerodha_login import ZerodhaLoginState
from app.integrations.zerodha import service


class StateRejected(Exception):
    """Only fixed reason codes may be logged; never state or request tokens."""


def create(db, initiating_session):
    # Revalidate under a session lock; logout either wins first or waits for insert.
    session = db.scalar(select(DashboardSession).where(DashboardSession.id == initiating_session.id)
                        .with_for_update().execution_options(populate_existing=True))
    moment = auth.now()
    if not valid_session(session, moment):
        raise StateRejected('session_invalid')
    account = service.single_account(db)
    raw = secrets.token_hex(32)
    db.add(ZerodhaLoginState(account_id=account.id, dashboard_session_id=session.id,
        state_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=min(auth.aware(session.expires_at), moment + timedelta(minutes=10))))
    db.commit()
    return raw


def valid_session(session, moment):
    return bool(session and auth.aware(session.expires_at) > moment
                and hmac.compare_digest(session.credential_version, auth.credential_version()))


def claim(db, raw):
    state = db.scalar(select(ZerodhaLoginState).where(ZerodhaLoginState.state_hash == hashlib.sha256(raw.encode()).hexdigest()))
    if state is None:
        raise StateRejected('state_unknown')
    session = db.scalar(select(DashboardSession).where(DashboardSession.id == state.dashboard_session_id)
                        .with_for_update().execution_options(populate_existing=True))
    moment = auth.now()
    if not valid_session(session, moment):
        raise StateRejected('session_invalid')
    account = service.single_account(db)
    if account.id != state.account_id:
        raise StateRejected('account_changed')
    # PostgreSQL evaluates the condition against current row state even when two
    # callbacks originally read the same unused row. RETURNING grants one winner.
    claimed = db.scalar(update(ZerodhaLoginState).where(
        ZerodhaLoginState.id == state.id, ZerodhaLoginState.consumed_at.is_(None),
        ZerodhaLoginState.expires_at > moment,
    ).values(consumed_at=moment).returning(ZerodhaLoginState.id)
      .execution_options(synchronize_session=False))
    if claimed is None:
        raise StateRejected('state_expired_or_used')
    # Durable BEFORE contacting Kite: a timeout/crash/write failure must never
    # make this correlation reusable. The user starts a fresh flow on any failure.
    db.commit()
