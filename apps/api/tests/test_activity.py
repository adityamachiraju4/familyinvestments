"""Execution accounting and orchestration with isolated storage and no network."""
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
import asyncio
import httpx
import pytest
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models import Holding, HoldingSnapshot, InvestmentTransaction, Order, PortfolioSnapshot, ZerodhaAccount, ZerodhaCredential
from app.main import app
from app.auth.service import require_access
from types import SimpleNamespace
from app.integrations.zerodha import service as zerodha
from app.integrations.zerodha.exceptions import credentials_error, provider_error, IntegrationError
from app.integrations.zerodha.routes import integration_db
from app.portfolio import activity, service as portfolio

DAY = date(2026, 10, 7)
HOLDING = dict(exchange='NSE', tradingsymbol='EXISTING', instrument_token=123, quantity=5, t1_quantity=0, average_price='100', last_price='110')
ORDER = dict(order_id='o1', exchange='NSE', tradingsymbol='NIFTYBEES', transaction_type='BUY', product='CNC', order_type='LIMIT', quantity=2, filled_quantity=2, price='282', average_price='281', status='COMPLETE', order_timestamp='2026-10-06 18:00:00', exchange_timestamp='2026-10-07 09:15:00')
TRADE = dict(trade_id='t1', order_id='o1', exchange='NSE', tradingsymbol='NIFTYBEES', instrument_token=456, product='CNC', transaction_type='BUY', quantity=1, average_price='280', fill_timestamp='2026-10-07 09:15:00')


class Provider:
    def __init__(self):
        self.calls = []
        self.holdings = [HOLDING]
        self.orders = [ORDER]
        self.trades = [TRADE, {**TRADE, 'trade_id':'t2', 'average_price':'282'}]
    def get_holdings(self):
        self.calls.append('holdings')
        return self.holdings
    def get_orders(self):
        self.calls.append('orders')
        return self.orders
    def get_trades(self):
        self.calls.append('trades')
        return self.trades
    def get_margins(self):
        self.calls.append('funds')
        return {'available': {'live_balance':'1000', 'cash':'-1'}, 'net':'900'}


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def configure(connection, record):
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))
        connection.execute('PRAGMA foreign_keys=ON')
    for model in (ZerodhaAccount, ZerodhaCredential, Holding, Order, InvestmentTransaction, PortfolioSnapshot, HoldingSnapshot):
        model.__table__.create(engine)
    from app.models.mutual_fund import MutualFundAccount, MutualFundScheme, SIP, MutualFundTransaction, MutualFundHolding
    for model in (MutualFundAccount, MutualFundScheme, SIP, MutualFundTransaction, MutualFundHolding):
        model.__table__.create(engine)
    monkeypatch.setattr(portfolio, 'today', lambda: DAY)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(ZerodhaAccount(id=42, client_id='LOCAL_DEV', display_name='Family', connection_status='connected'))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def provider(monkeypatch):
    source = Provider()
    monkeypatch.setattr(zerodha, 'authenticated_client', lambda db, account: source)
    return source


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def call(db, path, method='GET'):
    async def run():
        app.dependency_overrides[require_access] = lambda: SimpleNamespace(token_hash="isolated-test-session")
        app.dependency_overrides[integration_db] = lambda: db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                return await client.request(method, path)
        finally:
            app.dependency_overrides.clear()
    return asyncio.run(run())


def test_canonical_refresh_sequence_and_idempotent_fills(db, provider):
    for _ in range(2):
        result = activity.refresh_portfolio(db)
        assert result.status == 'ok'
        assert (result.holdings_synced, result.orders_synced, result.trades_synced) == (1, 1, 2)
        assert result.summary.total_account_value == Decimal('1550')
    assert provider.calls == ['holdings','orders','trades','funds'] * 2
    assert count(db, Order) == 1 and count(db, InvestmentTransaction) == 2
    assert count(db, PortfolioSnapshot) == 1 and count(db, HoldingSnapshot) == 1
    assert count(db, Holding) == 1
    result = call(db, '/portfolio/activity/today').json()
    assert len(result['executed']) == 1
    fill = result['executed'][0]
    assert fill['quantity'] == 2 and fill['fill_count'] == 2
    assert Decimal(fill['average_price']) == Decimal('281')
    assert Decimal(fill['amount']) == Decimal('562')
    assert fill['bucket'] == 'NIFTY_50' and fill['transaction_type'] == 'BUY'
    assert fill['holding_status'] == 'AWAITING_HOLDINGS'
    assert fill['charges'] is None
    assert all(t.charges is None and t.net_amount is None for t in db.scalars(select(InvestmentTransaction)))
    assert result['orders'][0]['timestamp'].startswith('2026-10-06')  # AMO retained in today's book.


@pytest.mark.parametrize('status,has_trades', [('REJECTED',False),('CANCELLED',False),('CANCELLED',True),('OPEN',True)])
def test_orders_never_substitute_for_executions(db, provider, status, has_trades):
    provider.orders = [{**ORDER, 'status':status, 'quantity':5, 'filled_quantity':2 if has_trades else 0}]
    provider.trades = provider.trades if has_trades else []
    activity.refresh_portfolio(db)
    result = activity.today_activity(db)
    assert len(result.executed) == int(has_trades)
    if has_trades:
        assert result.executed[0].quantity == 2  # Never the 5 requested units.
    assert result.rejected_cancelled_count == int(status in {'REJECTED','CANCELLED'})
    assert result.open_pending_count == int(status == 'OPEN')


def test_sell_and_non_delivery_are_activity_not_contributions(db, provider):
    provider.orders = []
    provider.trades += [{**TRADE, 'trade_id':'sell', 'order_id':'s1', 'transaction_type':'SELL'},
                        {**TRADE, 'trade_id':'intraday', 'order_id':'i1', 'product':'MIS'}]
    activity.refresh_portfolio(db)
    result = activity.today_activity(db)
    assert {row.transaction_type for row in result.executed} == {'BUY', 'SELL'}
    sell = next(row for row in result.executed if row.transaction_type == 'SELL')
    assert sell.holding_status == 'NOT_APPLICABLE'
    contribution = activity.contributions(db)
    assert contribution.recorded_buy_amount == Decimal('562')
    assert contribution.allocation['NIFTY_50'] == Decimal('562')
    assert contribution.recorded_from == DAY and contribution.history_complete is False
    assert contribution.charges is None


def test_present_holding_does_not_double_count_or_claim_attribution(db, provider):
    provider.holdings.append({**HOLDING, 'tradingsymbol':'NIFTYBEES', 'quantity':2, 'instrument_token':456})
    result = activity.refresh_portfolio(db)
    execution = activity.today_activity(db).executed[0]
    assert execution.holding_status == 'HOLDING_PRESENT_UNCONFIRMED'
    assert result.summary.holdings_market_value == Decimal('770')
    assert result.summary.total_account_value == Decimal('1770')
    assert activity.today_activity(db).awaiting_holdings == []


@pytest.mark.parametrize('component', ['holdings','orders','trades','funds'])
def test_fetch_failure_preserves_all_database_state(db, provider, monkeypatch, component):
    activity.refresh_portfolio(db)
    before = zerodha.single_account(db).last_refresh_at
    existing = db.scalar(select(Holding))
    provider.holdings = []
    def fail():
        raise provider_error()
    monkeypatch.setattr(provider, 'get_' + ('margins' if component == 'funds' else component), fail)
    with pytest.raises(IntegrationError):
        activity.refresh_portfolio(db)
    db.refresh(existing)
    assert existing.is_active is True
    assert count(db, Order) == 1 and count(db, InvestmentTransaction) == 2
    assert zerodha.single_account(db).last_refresh_at == before
    assert db.scalar(select(PortfolioSnapshot)).holdings_market_value == Decimal('550')


@pytest.mark.parametrize('failure_point', ['orders','investment_transactions','holding_snapshots','commit'])
def test_persistence_failure_rolls_back_whole_refresh(db, provider, monkeypatch, failure_point):
    activity.refresh_portfolio(db)
    before = zerodha.single_account(db).last_refresh_at
    provider.holdings = []
    provider.trades.append({**TRADE, 'trade_id':'new'})
    provider.orders = [{**ORDER, 'quantity':3, 'filled_quantity':3}]
    execute = db.execute
    def fail(statement, *args, **kwargs):
        table = getattr(statement, 'table', None)
        # With no holdings, snapshot generation deletes obsolete current membership.
        if table is not None and table.name == failure_point:
            raise OperationalError(None, None, Exception('private'))
        return execute(statement, *args, **kwargs)
    monkeypatch.setattr(db, 'execute', fail)
    if failure_point == 'commit':
        monkeypatch.setattr(db, 'commit', MagicMock(side_effect=OperationalError(None,None,Exception('private'))))
    with pytest.raises(IntegrationError) as exc:
        activity.refresh_portfolio(db)
    assert 'private' not in str(exc.value)
    assert db.scalar(select(Holding)).is_active is True
    assert count(db, InvestmentTransaction) == 2
    assert db.scalar(select(Order)).quantity == 2
    assert count(db, HoldingSnapshot) == 1
    assert db.scalar(select(PortfolioSnapshot)).holdings_market_value == Decimal('550')
    assert zerodha.single_account(db).last_refresh_at == before


@pytest.mark.parametrize('kind', ['bad_order','bad_trade','duplicate','wrong_date','overfill','inconsistent'])
def test_malformed_books_rejected_before_reconciliation(db, provider, kind):
    activity.refresh_portfolio(db)
    provider.holdings = []
    if kind == 'bad_order': provider.orders = [{}]
    if kind == 'bad_trade': provider.trades = [{}]
    if kind == 'duplicate': provider.trades = [TRADE, TRADE]
    if kind == 'wrong_date': provider.trades = [{**TRADE,'fill_timestamp':'2026-10-06 09:15:00'}]
    if kind == 'overfill': provider.trades = [{**TRADE,'quantity':3}]
    if kind == 'inconsistent': provider.trades = [{**TRADE,'transaction_type':'SELL'}]
    with pytest.raises(IntegrationError): activity.refresh_portfolio(db)
    assert db.scalar(select(Holding)).is_active is True
    assert count(db, InvestmentTransaction) == 2


def test_fresh_guard_skips_remote_requests_and_does_not_loop(db, provider):
    activity.refresh_portfolio(db)
    provider.calls.clear()
    for _ in range(3):
        assert activity.refresh_portfolio(db, if_stale=True).status == 'fresh'
    assert provider.calls == []
    assert count(db, InvestmentTransaction) == 2


def test_expired_token_normalized_without_writes(db, monkeypatch):
    monkeypatch.setattr(zerodha,'authenticated_client',MagicMock(side_effect=credentials_error()))
    result = call(db, '/portfolio/refresh', 'POST')
    assert result.status_code == 200 and result.json()['status'] == 'reconnect_required'
    assert count(db, Holding) == count(db, InvestmentTransaction) == count(db, PortfolioSnapshot) == 0


def test_previous_history_untouched_and_fill_ids_day_scoped(db, provider, monkeypatch):
    activity.refresh_portfolio(db)
    snapshot = db.scalar(select(PortfolioSnapshot))
    old_id, old_value = snapshot.id, snapshot.total_account_value
    monkeypatch.setattr(portfolio, 'today', lambda: date(2026,10,8))
    provider.holdings = []
    provider.trades = [{**TRADE, 'fill_timestamp':'2026-10-08 09:15:00'}]
    activity.refresh_portfolio(db)
    db.refresh(snapshot)
    assert snapshot.id == old_id and snapshot.total_account_value == old_value
    assert count(db, HoldingSnapshot) == 1  # Yesterday's row remains.
    assert count(db, InvestmentTransaction) == 3  # Same exchange trade ID on a new day.


def test_conflicting_fill_replay_cannot_rewrite_financial_history(db, provider):
    activity.refresh_portfolio(db)
    provider.holdings = []
    provider.trades = [{**TRADE, 'average_price':'999'}]
    with pytest.raises(IntegrationError):
        activity.refresh_portfolio(db)
    assert db.scalar(select(Holding)).is_active is True
    assert activity.contributions(db).recorded_buy_amount == Decimal('562')


def test_same_day_round_trip_not_mislabelled_awaiting_holdings(db, provider):
    provider.orders = []
    provider.trades.append({**TRADE,'trade_id':'sold','order_id':'sell','transaction_type':'SELL','quantity':2})
    activity.refresh_portfolio(db)
    result = activity.today_activity(db)
    buy = next(row for row in result.executed if row.transaction_type == 'BUY')
    assert buy.holding_status == 'NETTED_BY_SELLS'
    assert result.awaiting_holdings == []
    # User-defined contributions are gross BUY purchases, never net sales cash flow.
    assert activity.contributions(db).recorded_buy_amount == Decimal('562')


def test_unknown_fill_and_holding_remain_visible_separate_from_other(db, provider):
    from app.models import Bucket
    provider.holdings = [{**HOLDING, 'tradingsymbol':'NEWETF'}]
    provider.orders = [{**ORDER, 'tradingsymbol':'NEWETF'}]
    provider.trades = [{**TRADE, 'tradingsymbol':'NEWETF'}]
    result = activity.refresh_portfolio(db)
    assert result.summary.holdings_market_value == Decimal('550')
    assert result.summary.allocation[Bucket.UNCLASSIFIED] == Decimal('550')
    assert result.summary.allocation[Bucket.OTHER] == 0
    fill = db.scalar(select(InvestmentTransaction))
    holding = db.scalar(select(Holding))
    assert fill.bucket == holding.bucket == Bucket.UNCLASSIFIED
    assert activity.today_activity(db).executed[0].bucket == Bucket.UNCLASSIFIED
    contributions = activity.contributions(db)
    assert contributions.allocation[Bucket.UNCLASSIFIED] == Decimal('280')
    assert contributions.allocation[Bucket.OTHER] == 0
    assert sum(contributions.allocation.values()) == contributions.recorded_buy_amount
    snapshot = db.scalar(select(PortfolioSnapshot))
    assert snapshot.unclassified_value == Decimal('550') and snapshot.other_value == 0


def test_real_contribution_breakdown_and_classification_only_replay(db, provider):
    from app.models import Bucket
    rows = [('NIFTYBEES', 2, '258.59'), ('MIDCAPETF', 40, '22.40'), ('HDFCSML250', 3, '180.12')]
    provider.orders = [{**ORDER, 'order_id':f'o{i}', 'tradingsymbol':symbol, 'quantity':qty, 'filled_quantity':qty, 'average_price':price} for i,(symbol,qty,price) in enumerate(rows)]
    provider.trades = [{**TRADE, 'order_id':f'o{i}', 'trade_id':f't{i}', 'tradingsymbol':symbol, 'quantity':qty, 'average_price':price} for i,(symbol,qty,price) in enumerate(rows)]
    activity.refresh_portfolio(db)
    fill = db.scalar(select(InvestmentTransaction).where(InvestmentTransaction.tradingsymbol=='HDFCSML250'))
    original = (fill.quantity, fill.price, fill.zerodha_trade_id, fill.zerodha_order_id, fill.fill_timestamp)
    fill.bucket = Bucket.OTHER  # Previously derived classification; not an execution change.
    db.commit()
    activity.refresh_portfolio(db)
    db.refresh(fill)
    assert fill.bucket == Bucket.SMALL_CAP
    assert original == (fill.quantity, fill.price, fill.zerodha_trade_id, fill.zerodha_order_id, fill.fill_timestamp)
    result = activity.contributions(db)
    assert result.allocation[Bucket.NIFTY_50] == Decimal('517.18')
    assert result.allocation[Bucket.MID_CAP] == Decimal('896')
    assert result.allocation[Bucket.SMALL_CAP] == Decimal('540.36')
    assert result.allocation[Bucket.OTHER] == result.allocation[Bucket.UNCLASSIFIED] == 0
    assert sum(result.allocation.values()) == result.recorded_buy_amount == Decimal('1953.54')


T1_PURCHASES = [
    dict(exchange='NSE', tradingsymbol='HDFCSML250', instrument_token=101,
         quantity=0, t1_quantity=3, average_price='180.12', last_price='180.12'),
    dict(exchange='NSE', tradingsymbol='MIDCAPETF', instrument_token=102,
         quantity=0, t1_quantity=40, average_price='22.40', last_price='22.40'),
    dict(exchange='NSE', tradingsymbol='NIFTYBEES', instrument_token=103,
         quantity=0, t1_quantity=2, average_price='258.59', last_price='258.59'),
]


@pytest.mark.parametrize('quantity,t1', [(0, 3), (3, 0), (3, 2)])
def test_delivery_effective_quantity_decimal(quantity, t1):
    row = zerodha.normalize_holding({**T1_PURCHASES[0], 'quantity': quantity,
                                    't1_quantity': t1, 'last_price': '181.13'}, 42,
                                   datetime.now(timezone.utc))
    assert row['quantity'] == quantity and row['t1_quantity'] == t1
    assert row['invested_value'] == Decimal('180.12') * (quantity + t1)
    assert row['current_value'] == Decimal('181.13') * (quantity + t1)
    assert isinstance(row['current_value'], Decimal)


def test_t1_settlement_values_snapshots_and_contributions(db, provider, monkeypatch):
    provider.holdings = T1_PURCHASES.copy()
    provider.orders = []
    provider.trades = [dict(TRADE, trade_id=f't1-{i}', order_id=f'purchase-{i}',
                           tradingsymbol=h['tradingsymbol'], instrument_token=h['instrument_token'],
                           quantity=h['t1_quantity'], average_price=h['average_price'])
                       for i, h in enumerate(T1_PURCHASES)]
    # Intraday fills never become delivery contributions or holdings.
    provider.trades.append(dict(TRADE, trade_id='mis', order_id='mis', product='MIS'))
    first = activity.refresh_portfolio(db)
    assert first.summary.holdings_invested_value == Decimal('1953.54')
    assert first.summary.holdings_market_value == Decimal('1953.54')
    assert first.summary.holding_count == 3
    assert first.summary.allocation['SMALL_CAP'] == Decimal('540.36')
    assert first.summary.allocation['MID_CAP'] == Decimal('896.00')
    assert first.summary.allocation['NIFTY_50'] == Decimal('517.18')
    assert activity.contributions(db).recorded_buy_amount == Decimal('1953.54')
    rows = portfolio.current_holdings(db, 42)
    identities = {row.tradingsymbol: row.id for row in rows}
    from app.integrations.zerodha.schemas import HoldingView
    for row in rows:
        view = HoldingView.model_validate(row)
        assert view.quantity == 0 and view.effective_quantity == view.t1_quantity > 0
        history = portfolio.holding_history(db, row.tradingsymbol, 10)
        assert history[0].quantity == view.effective_quantity
        assert history[0].market_value == row.current_value
    snapshot = db.scalar(select(PortfolioSnapshot))
    assert snapshot.holdings_invested_value == snapshot.holdings_market_value == Decimal('1953.54')
    snapshot_id = snapshot.id
    provider.holdings = [dict(h, quantity=h['t1_quantity'], t1_quantity=0) for h in T1_PURCHASES]
    for _ in range(2):
        settled = activity.refresh_portfolio(db)
        assert settled.summary.holdings_invested_value == first.summary.holdings_invested_value
        assert settled.summary.holdings_market_value == first.summary.holdings_market_value
        assert settled.summary.holding_count == 3
        assert activity.contributions(db).recorded_buy_amount == Decimal('1953.54')
    assert {row.tradingsymbol: row.id for row in portfolio.current_holdings(db, 42)} == identities
    assert count(db, InvestmentTransaction) == 4  # Three CNC fills and one MIS fill, each once.
    assert count(db, HoldingSnapshot) == 3 and count(db, PortfolioSnapshot) == 1
    assert db.scalar(select(PortfolioSnapshot)).id == snapshot_id
    # A partial invalid list and a failed fetch cannot reconcile active rows away.
    provider.holdings = [T1_PURCHASES[0], {'tradingsymbol': 'invalid'}]
    with pytest.raises(IntegrationError):
        activity.refresh_portfolio(db)
    assert len(portfolio.current_holdings(db, 42)) == 3
    with monkeypatch.context() as patch:
        patch.setattr(provider, 'get_holdings', MagicMock(side_effect=provider_error()))
        with pytest.raises(IntegrationError):
            activity.refresh_portfolio(db)
    assert len(portfolio.current_holdings(db, 42)) == 3
    provider.holdings = T1_PURCHASES[:1]
    activity.refresh_portfolio(db)
    assert len(portfolio.current_holdings(db, 42)) == 1
    assert count(db, Holding) == 3
