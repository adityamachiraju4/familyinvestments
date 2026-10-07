"""Read-only day books and atomic, scheduler-ready dashboard refresh.

External reads are bounded and validated before any database writes. One account
lock covers fetch-through-commit, serializing this service with holdings sync and
snapshot creation. Remote reads are sequential, not a brokerage transaction.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.integrations.zerodha import service as zerodha
from app.integrations.zerodha.activity_schemas import INDIA, ProviderOrder, ProviderTrade
from app.integrations.zerodha.buckets import classify_instrument
from app.integrations.zerodha.exceptions import IntegrationError, credentials_error, provider_error
from app.models import Bucket, InvestmentTransaction, Order
from app.portfolio import service as portfolio
from app.portfolio.activity_schemas import ActivityView, ContributionsView, ExecutionView, OrderActivityView, RefreshResult

FRESHNESS = timedelta(minutes=5)


def refresh_required(last_refresh_at: datetime | None, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if last_refresh_at is None:
        return True
    last = last_refresh_at.replace(tzinfo=timezone.utc) if last_refresh_at.tzinfo is None else last_refresh_at
    return last.astimezone(INDIA).date() != now.astimezone(INDIA).date() or not timedelta(0) <= now - last < FRESHNESS


def money(value: Decimal) -> Decimal:
    value = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if abs(value) >= Decimal("1e16"):
        raise provider_error()
    return value


def validated_books(order_payload, trade_payload, day):
    try:
        if not isinstance(order_payload, list) or not isinstance(trade_payload, list):
            raise provider_error()
        orders = [ProviderOrder.model_validate(row) for row in order_payload]
        trades = [ProviderTrade.model_validate(row) for row in trade_payload]
        if len({row.order_id for row in orders}) != len(orders):
            raise provider_error()
        keys = [(row.exchange, row.order_id, row.trade_id) for row in trades]
        if len(set(keys)) != len(keys):
            raise provider_error()
        if any(row.fill_timestamp.date() != day for row in trades):
            raise provider_error()
        # AMO context may be yesterday; the book itself is today's provider response.
        if any(row.order_timestamp.date() > day for row in orders):
            raise provider_error()
        by_id = {row.order_id: row for row in orders}
        fill_quantities = defaultdict(int)
        for row in trades:
            money(row.average_price * row.quantity)
            money(row.average_price)
            order = by_id.get(row.order_id)
            if order is not None:
                if (row.exchange, row.tradingsymbol, row.product, row.transaction_type) != (
                    order.exchange, order.tradingsymbol, order.product, order.transaction_type,
                ):
                    raise provider_error()
                fill_quantities[row.order_id] += row.quantity
                if fill_quantities[row.order_id] > order.quantity:
                    raise provider_error()
        for row in orders:
            money(row.price)
            money(row.average_price)
        return orders, trades
    except (ValidationError, ArithmeticError):
        raise provider_error() from None


def validate_existing_fills(db: Session, account_id: int, trades, day):
    """A replay may not silently rewrite a recorded financial execution."""
    existing = {(row.exchange, row.zerodha_order_id, row.zerodha_trade_id): row
                for row in db.scalars(select(InvestmentTransaction).where(
                    InvestmentTransaction.account_id == account_id,
                    InvestmentTransaction.trade_date == day,
                    InvestmentTransaction.zerodha_trade_id.is_not(None),
                ))}
    for fill in trades:
        stored = existing.get((fill.exchange, fill.order_id, fill.trade_id))
        if stored is not None and (
            stored.tradingsymbol, stored.transaction_type, stored.product,
            stored.quantity, stored.price, stored.gross_amount,
        ) != (fill.tradingsymbol, fill.transaction_type, fill.product, fill.quantity,
              money(fill.average_price), money(fill.quantity * fill.average_price)):
            raise provider_error()


def persist_books(db: Session, account_id: int, orders, trades, day, now):
    for row in orders:
        data = row.model_dump(exclude={"order_id"})
        data.update(account_id=account_id, zerodha_order_id=row.order_id, book_date=day, synced_at=now)
        data["price"], data["average_price"] = money(row.price), money(row.average_price)
        stmt = insert(Order).values(**data)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[Order.account_id, Order.zerodha_order_id],
            set_={key: value for key, value in data.items() if key not in {"account_id", "zerodha_order_id"}},
        ))
    for row in trades:
        order_id = db.scalar(select(Order.id).where(
            Order.account_id == account_id, Order.zerodha_order_id == row.order_id,
        ))
        data = dict(account_id=account_id, order_id=order_id, trade_date=day,
                    zerodha_trade_id=row.trade_id, zerodha_order_id=row.order_id,
                    tradingsymbol=row.tradingsymbol, exchange=row.exchange,
                    instrument_token=row.instrument_token, product=row.product,
                    transaction_type=row.transaction_type, quantity=row.quantity,
                    price=money(row.average_price), gross_amount=money(row.quantity * row.average_price),
                    bucket=classify_instrument(row.tradingsymbol, row.exchange, row.instrument_token), fill_timestamp=row.fill_timestamp,
                    charges=None, net_amount=None, synced_at=now)
        stmt = insert(InvestmentTransaction).values(**data)
        # Fills are immutable events. Repeated fetches only attach missing order context
        # and correct derived classification/refresh observation time; a different identity is a separate fill.
        db.execute(stmt.on_conflict_do_update(
            index_elements=[InvestmentTransaction.account_id, InvestmentTransaction.trade_date,
                            InvestmentTransaction.exchange, InvestmentTransaction.zerodha_order_id,
                            InvestmentTransaction.zerodha_trade_id],
            set_={"order_id": order_id, "synced_at": now, "bucket": data["bucket"]},
        ))
    db.expire_all()


def refresh_portfolio(db: Session, *, if_stale: bool = False) -> RefreshResult:
    """No HTTP dependency: suitable for a future external job using a DB session."""
    try:
        account = zerodha.lock_account(db)
        if account.connection_status != "connected":
            raise credentials_error()
        client = zerodha.authenticated_client(db, account)
        now = datetime.now(timezone.utc)
        if if_stale and not refresh_required(account.last_refresh_at, now):
            result = RefreshResult(status="fresh", last_refresh_at=account.last_refresh_at)
            db.rollback()  # Release the lock without updating anything.
            return result
        day = portfolio.today()
        holding_payload = client.get_holdings()
        rows = zerodha.validated_holdings(holding_payload, account.id, now)
        order_payload = client.get_orders()
        trade_payload = client.get_trades()
        orders, trades = validated_books(order_payload, trade_payload, day)
        validate_existing_fills(db, account.id, trades, day)
        funds = zerodha.normalize_funds(client.get_margins())
        if portfolio.today() != day:
            raise IntegrationError("day_changed", "The trading day changed. Refresh again.", 409)
        zerodha.persist_holdings(db, account, rows, now)
        persist_books(db, account.id, orders, trades, day, now)
        portfolio.snapshot_today(db, current_funds=funds, commit=False)
        account.last_refresh_at = datetime.now(timezone.utc)
        values = portfolio.calculate_summary(portfolio.current_holdings(db, account.id), funds.available_cash, account.last_sync_at)
        result = RefreshResult(status="ok", last_refresh_at=account.last_refresh_at,
                               holdings_synced=len(rows), orders_synced=len(orders), trades_synced=len(trades), summary=values)
        db.commit()
        return result
    except IntegrationError as exc:
        db.rollback()
        if exc.code == "credentials_invalid":
            return RefreshResult(status="reconnect_required")
        raise
    except SQLAlchemyError:
        db.rollback()
        raise IntegrationError("database_unavailable", "Dashboard refresh failed. Please try again.") from None
    except Exception:
        db.rollback()
        raise


def today_activity(db: Session) -> ActivityView:
    account = zerodha.single_account(db)
    day = portfolio.today()
    orders = db.scalars(select(Order).where(Order.account_id == account.id, Order.book_date == day)
                        .order_by(Order.order_timestamp.desc(), Order.id)).all()
    trades = db.scalars(select(InvestmentTransaction).where(
        InvestmentTransaction.account_id == account.id, InvestmentTransaction.trade_date == day,
        InvestmentTransaction.zerodha_trade_id.is_not(None),
    ).order_by(InvestmentTransaction.fill_timestamp, InvestmentTransaction.id)).all()
    holdings = portfolio.current_holdings(db, account.id)
    groups = defaultdict(list)
    for row in trades:
        groups[(row.zerodha_order_id, row.exchange, row.tradingsymbol, row.transaction_type, row.product)].append(row)
    net_quantities = defaultdict(int)
    for row in trades:
        if row.product == "CNC":
            net_quantities[(row.exchange, row.tradingsymbol)] += row.quantity * (1 if row.transaction_type == "BUY" else -1)
    executed = []
    for (order_id, exchange, symbol, direction, product), fills in groups.items():
        quantity = sum(row.quantity for row in fills)
        amount = sum((row.gross_amount for row in fills), Decimal(0))
        status = "NOT_APPLICABLE"
        if direction == "BUY" and product == "CNC":
            same = [h for h in holdings if h.exchange == exchange and h.tradingsymbol == symbol]
            matching_quantity = sum(h.quantity + h.t1_quantity for h in same)
            net_buys = net_quantities[(exchange, symbol)]
            status = ("NETTED_BY_SELLS" if net_buys <= 0 else
                      "AWAITING_HOLDINGS" if matching_quantity < net_buys else "HOLDING_PRESENT_UNCONFIRMED")
        executed.append(ExecutionView(symbol=symbol, exchange=exchange, transaction_type=direction,
            product=product, quantity=quantity, average_price=amount / quantity, amount=amount,
            bucket=classify_instrument(symbol, exchange, fills[0].instrument_token), executed_at=max(row.fill_timestamp for row in fills),
            order_id=order_id, fill_count=len(fills), holding_status=status))
    last = account.last_refresh_at
    if last is not None:
        last = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
        if last.astimezone(INDIA).date() != day:
            last = None
    return ActivityView(date=day, last_synced_at=last, executed=executed,
        orders=[OrderActivityView(symbol=o.tradingsymbol, exchange=o.exchange,
            transaction_type=o.transaction_type, product=o.product, quantity=o.quantity,
            filled_quantity=o.filled_quantity, status=o.status, average_price=o.average_price,
            timestamp=o.order_timestamp, order_id=o.zerodha_order_id) for o in orders],
        awaiting_holdings=[e for e in executed if e.holding_status == "AWAITING_HOLDINGS"],
        open_pending_count=sum(o.status not in {"COMPLETE", "REJECTED", "CANCELLED"} for o in orders),
        rejected_cancelled_count=sum(o.status in {"REJECTED", "CANCELLED"} for o in orders))


def contributions(db: Session) -> ContributionsView:
    account = zerodha.single_account(db)
    month = portfolio.today().replace(day=1)
    rows = db.scalars(select(InvestmentTransaction).where(
        InvestmentTransaction.account_id == account.id,
        InvestmentTransaction.trade_date >= month, InvestmentTransaction.trade_date <= portfolio.today(),
        InvestmentTransaction.zerodha_trade_id.is_not(None),
        InvestmentTransaction.transaction_type == "BUY", InvestmentTransaction.product == "CNC",
    )).all()
    earliest = db.scalar(select(InvestmentTransaction.trade_date).where(
        InvestmentTransaction.account_id == account.id, InvestmentTransaction.zerodha_trade_id.is_not(None),
    ).order_by(InvestmentTransaction.trade_date).limit(1))
    allocation = {bucket: Decimal(0) for bucket in Bucket}
    for row in rows:
        allocation[classify_instrument(row.tradingsymbol, row.exchange, row.instrument_token)] += row.gross_amount
    from app.investments.service import monthly_contributions
    mf_amount = monthly_contributions(db)
    return ContributionsView(month=month, recorded_from=earliest, monthly_mf_contributions=mf_amount,
                             total_recorded_invested=sum(allocation.values(), Decimal(0)) + mf_amount,
                             recorded_buy_amount=sum(allocation.values(), Decimal(0)), allocation=allocation)
