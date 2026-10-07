"""Read-only MIS positions; never infer P&L from unmatched executions."""
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal
from pydantic import BaseModel, Field, StrictInt, ValidationError
from sqlalchemy import select
from app.models import InvestmentTransaction
from app.integrations.zerodha import service as zerodha
from app.integrations.zerodha.exceptions import IntegrationError, provider_error
from app.portfolio import service

# Bound magnitude, not provider fractional precision: Kite decimals may contain
# floating-point noise. Preserve turnover/prices; normalize only displayed P&L.
LIMIT = Decimal("1e16")
Amount = Field(ge=0, lt=LIMIT, allow_inf_nan=False)
PnL = Field(default=None, gt=-LIMIT, lt=LIMIT, allow_inf_nan=False)


def display_pnl(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    # Project-standard money precision, independent of ambient Decimal context.
    with localcontext() as context:
        context.prec = 28
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class ProviderPosition(BaseModel):
    tradingsymbol: str = Field(min_length=1, max_length=128)
    exchange: str = Field(min_length=1, max_length=16)
    product: str
    quantity: StrictInt
    overnight_quantity: StrictInt | None = None
    buy_quantity: StrictInt = Field(ge=0)
    sell_quantity: StrictInt = Field(ge=0)
    buy_price: Decimal = Amount
    sell_price: Decimal = Amount
    buy_value: Decimal = Amount
    sell_value: Decimal = Amount
    realised: Decimal | None = PnL
    unrealised: Decimal | None = PnL


class IntradayPosition(BaseModel):
    symbol: str
    exchange: str
    product: Literal['MIS'] = 'MIS'
    activity_type: Literal['INTRADAY'] = 'INTRADAY'
    buy_quantity: int
    sell_quantity: int
    open_quantity: int | None
    average_buy_price: Decimal | None
    average_sell_price: Decimal | None
    buy_value: Decimal
    sell_value: Decimal
    realised_pnl: Decimal | None = None
    unrealised_pnl: Decimal | None = None
    status: Literal['OPEN', 'CLOSED', 'UNCONFIRMED']
    source: Literal['provider_positions', 'recorded_fills']
    fill_count: int


class IntradayView(BaseModel):
    date: date
    observed_at: datetime | None
    positions_available: bool
    positions: list[IntradayPosition]


def today_intraday(db):
    account = zerodha.single_account(db)
    day = service.today()
    fills = db.scalars(select(InvestmentTransaction).where(
        InvestmentTransaction.account_id == account.id,
        InvestmentTransaction.trade_date == day,
        InvestmentTransaction.zerodha_trade_id.is_not(None),
        InvestmentTransaction.product == 'MIS')).all()
    groups = defaultdict(list)
    for row in fills:
        groups[(row.exchange, row.tradingsymbol)].append(row)
    try:
        payload = zerodha.authenticated_client(db, account).get_positions()
        books = parse_positions(payload)
        if service.today() != day:
            raise provider_error()
    except IntegrationError as exc:
        if exc.code != 'provider_error':
            raise
        # Only live provider availability/parsing failures degrade to recorded fills.
        return IntradayView(date=day, observed_at=None, positions_available=False,
            positions=[from_fills(key, rows) for key, rows in sorted(groups.items())])
    result = []
    for key in sorted(set(books['day']) | set(books['net']) | set(groups)):
        row = books['day'].get(key)
        net = books['net'].get(key)
        if row is None and net is not None and net.overnight_quantity == 0:
            row = net  # MIS with no carry uses the same day's net turnover.
        # A missing day book or inconsistent/overnight MIS identity cannot
        # safely provide today's turnover and P&L. Retain fills as context.
        if row is None:
            if key in groups: result.append(from_fills(key, groups[key]))
            continue
        trusted = (net is not None and net.overnight_quantity == 0 and row.overnight_quantity == 0
                   and net.quantity == row.quantity == row.buy_quantity - row.sell_quantity
                   and net.buy_quantity == row.buy_quantity and net.sell_quantity == row.sell_quantity)
        quantity = net.quantity if trusted else None
        result.append(IntradayPosition(symbol=key[1],exchange=key[0],
            buy_quantity=row.buy_quantity,sell_quantity=row.sell_quantity,
            open_quantity=quantity,average_buy_price=row.buy_price if row.buy_quantity else None,
            average_sell_price=row.sell_price if row.sell_quantity else None,
            buy_value=row.buy_value,sell_value=row.sell_value,
            realised_pnl=display_pnl(net.realised) if trusted else None,
            unrealised_pnl=display_pnl(net.unrealised) if trusted else None,
            status='UNCONFIRMED' if quantity is None else 'CLOSED' if quantity == 0 else 'OPEN',
            source='provider_positions',fill_count=len(groups[key])))
    return IntradayView(date=day,observed_at=datetime.now(timezone.utc),positions_available=True,positions=result)


def parse_positions(payload):
    """Validate external books only; output construction errors must propagate."""
    try:
        if not isinstance(payload, dict) or any(not isinstance(payload.get(key), list) for key in ('net', 'day')):
            raise provider_error()
        books = {}
        for book in ('net', 'day'):
            if any(not isinstance(row, dict) or not isinstance(row.get('product'), str)
                   or not row['product'] for row in payload[book]):
                raise provider_error()
            rows = [ProviderPosition.model_validate(row) for row in payload[book] if row['product'] == 'MIS']
            keys = [(row.exchange, row.tradingsymbol) for row in rows]
            if len(set(keys)) != len(keys): raise provider_error()
            books[book] = dict(zip(keys, rows))
        return books
    except ValidationError:
        raise provider_error() from None


def from_fills(key, rows):
    buys = [row for row in rows if row.transaction_type == 'BUY']
    sells = [row for row in rows if row.transaction_type == 'SELL']
    bq, sq = sum(row.quantity for row in buys), sum(row.quantity for row in sells)
    bv = sum((row.gross_amount for row in buys), Decimal(0))
    sv = sum((row.gross_amount for row in sells), Decimal(0))
    return IntradayPosition(symbol=key[1],exchange=key[0],buy_quantity=bq,sell_quantity=sq,
        open_quantity=bq-sq,average_buy_price=bv/bq if bq else None,average_sell_price=sv/sq if sq else None,
        buy_value=bv,sell_value=sv,status='UNCONFIRMED',source='recorded_fills',fill_count=len(rows))
