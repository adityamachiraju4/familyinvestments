"""Portfolio arithmetic, snapshot transactions and history using isolated storage."""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.auth.service import require_access
from types import SimpleNamespace
from app.models import Bucket, Holding, HoldingSnapshot, MonthlyTarget, PortfolioSnapshot, ZerodhaAccount
from app.integrations.zerodha import service as zerodha
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.routes import integration_db
from app.integrations.zerodha.schemas import Funds
from app.portfolio import service
from scripts.seed_monthly_target import seed_target

DAY = date(2026, 10, 6)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def configure(connection, record):
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))
        connection.execute('PRAGMA foreign_keys=ON')
    # SQLite cannot execute PostgreSQL's EXTRACT check. Use a copied table with
    # an equivalent SQLite day check; the original PG constraint is tested elsewhere.
    from sqlalchemy import CheckConstraint, MetaData
    metadata = MetaData()
    for model in (ZerodhaAccount, Holding, PortfolioSnapshot, HoldingSnapshot, MonthlyTarget):
        model.__table__.to_metadata(metadata)
    target = metadata.tables['monthly_targets']
    for constraint in list(target.constraints):
        if isinstance(constraint, CheckConstraint):
            target.constraints.remove(constraint)
    target.append_constraint(CheckConstraint("strftime('%d', month) = '01'", name='month_first_day'))
    metadata.create_all(engine)
    monkeypatch.setattr(service, 'today', lambda: DAY)
    monkeypatch.setattr(zerodha, 'funds', lambda db: Funds(available_cash=Decimal('5099.50')))
    # Any unintended network call is a test failure.
    monkeypatch.setattr(zerodha.KiteClient, '_request', lambda *a, **kw: pytest.fail('Unexpected provider request'))
    with sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(ZerodhaAccount(client_id='LOCAL_DEV', display_name='Primary', connection_status='connected'))
        session.commit()
        yield session
    engine.dispose()


def add_holding(db, symbol='NIFTYBEES', bucket=Bucket.NIFTY_50, invested='100', market='120'):
    account = zerodha.single_account(db)
    row = Holding(account_id=account.id, exchange='NSE', tradingsymbol=symbol,
                  instrument_token=123, quantity=10, t1_quantity=0,
                  average_price=Decimal(invested) / 10, last_price=Decimal(market) / 10,
                  invested_value=Decimal(invested), current_value=Decimal(market),
                  unrealised_pnl=Decimal(market) - Decimal(invested), unrealised_pnl_percent=Decimal(20),
                  bucket=bucket, synced_at=datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    return row


def request(db, path, method='GET'):
    async def run():
        app.dependency_overrides[require_access] = lambda: SimpleNamespace(token_hash="isolated-test-session")
        app.dependency_overrides[integration_db] = lambda: db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                return await client.request(method, path)
        finally:
            app.dependency_overrides.clear()
    return asyncio.run(run())


@pytest.mark.parametrize('payload,current', [
    ({'net': '5099.5', 'available': {'cash': '-1123.5', 'opening_balance': '-1123.5', 'intraday_payin': '6223', 'live_balance': '5099.5'}}, '5099.5'),
    ({'net': '5099.5', 'available': {'cash': '-1123.5', 'opening_balance': '-1123.5'}}, '5099.5'),
    ({'net': '0', 'available': {'cash': '100', 'live_balance': '0'}}, '0'),
    ({'net': '12.123456789012345678'}, '12.123456789012345678'),
    ({'available': {'cash': '-10'}}, '-10'),
    ({'available': {'live_balance': None, 'cash': '20'}, 'net': '5'}, '5'),
])
def test_funds_priority_decimal_safe(payload, current):
    result = zerodha.normalize_funds(payload)
    assert result.available_cash == Decimal(current)
    assert isinstance(result.available_cash, Decimal)
    if 'opening_balance' in payload.get('available', {}):
        assert result.opening_balance == Decimal('-1123.5')


@pytest.mark.parametrize('payload', [None, [], {}, {'available': {}}, {'available': []},
    {'available': {'opening_balance': '10'}}, {'available': {'live_balance': 'invalid'}, 'net': '10'},
    {'available': {'live_balance': 'NaN'}}, {'net': 'Infinity'}, {'net': True}])
def test_malformed_funds_rejected(payload):
    with pytest.raises(IntegrationError) as exc:
        zerodha.normalize_funds(payload)
    assert exc.value.code == 'provider_error'


def test_summary_arbitrary_holdings_cash_excluded_from_pnl(db):
    for index in range(10):
        add_holding(db, f'STOCK{index}', bucket=list(Bucket)[index % 5], invested='100.10', market='120.20')
    response = request(db, '/portfolio/summary')
    assert response.status_code == 200
    values = response.json()
    assert Decimal(values['holdings_invested_value']) == Decimal('1001.0')
    assert Decimal(values['holdings_market_value']) == Decimal('1202.0')
    assert Decimal(values['total_account_value']) == Decimal('6301.5')
    assert Decimal(values['total_pnl']) == Decimal('201.0')
    assert values['holding_count'] == 10
    assert set(values['allocation']) == {b.value for b in Bucket}
    assert sum(map(Decimal, values['allocation'].values())) == Decimal('1202.0')


def test_empty_and_zero_cost_summary(db):
    values = service.summary(db)
    assert values.holding_count == 0 and values.total_pnl_percent == 0
    assert values.total_account_value == Decimal('5099.50')
    add_holding(db, invested='0', market='120')
    values = service.summary(db)
    assert values.total_pnl == Decimal('120') and values.total_pnl_percent == 0


def test_daily_and_holding_snapshots_idempotent(db):
    holding = add_holding(db)
    first = service.snapshot_today(db)
    assert first.snapshot_date == DAY and first.portfolio_value == Decimal('120')
    assert first.day_pnl == 0 and first.total_account_value == Decimal('5219.5')
    first_id, created = first.id, first.created_at
    child = db.scalar(select(HoldingSnapshot))
    child_id = child.id
    holding.current_value = Decimal('150')
    holding.last_price = Decimal('15')
    holding.unrealised_pnl = Decimal('50')
    db.commit()
    response = request(db, '/portfolio/snapshots/today', 'POST')
    assert response.status_code == 200
    assert Decimal(response.json()['holdings_market_value']) == Decimal('150')
    assert db.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 1
    assert db.scalar(select(func.count()).select_from(HoldingSnapshot)) == 1
    db.refresh(first)
    db.refresh(child)
    assert first.id == first_id and first.created_at == created
    assert child.id == child_id and child.market_value == Decimal('150')


def test_snapshot_largecap_residual_conserves_allocation(db):
    add_holding(db, bucket=Bucket.LARGE_CAP)
    snapshot = service.snapshot_today(db)
    assert snapshot.other_value == Decimal('120')
    assert snapshot.nifty_value + snapshot.midcap_value + snapshot.smallcap_value + snapshot.other_value == snapshot.holdings_market_value


def test_snapshot_requires_connected_account(db):
    zerodha.single_account(db).connection_status = 'disconnected'
    db.commit()
    assert request(db, '/portfolio/snapshots/today', 'POST').status_code == 401
    assert db.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 0


@pytest.mark.parametrize('existing', [False, True])
def test_snapshot_failure_rolls_back_every_write(db, monkeypatch, existing):
    holding = add_holding(db)
    if existing:
        service.snapshot_today(db)
    holding.current_value = Decimal('200')
    db.commit()
    execute = db.execute
    def fail_on_child(statement, *args, **kwargs):
        if getattr(statement, 'is_insert', False) and statement.table.name == 'holding_snapshots':
            raise OperationalError(None, None, Exception('secret database details'))
        return execute(statement, *args, **kwargs)
    monkeypatch.setattr(db, 'execute', fail_on_child)
    with pytest.raises(IntegrationError) as exc:
        service.snapshot_today(db)
    assert 'secret' not in str(exc.value)
    snapshots = db.scalars(select(PortfolioSnapshot)).all()
    assert len(snapshots) == int(existing)
    assert db.scalar(select(func.count()).select_from(HoldingSnapshot)) == int(existing)
    if existing:
        assert snapshots[0].holdings_market_value == Decimal('120')


def test_history_recent_limit_in_chronological_order(db, monkeypatch):
    add_holding(db)
    for day in (date(2026, 10, 4), date(2026, 10, 6), date(2026, 10, 5)):
        monkeypatch.setattr(service, 'today', lambda day=day: day)
        service.snapshot_today(db)
    for path in ('/portfolio/snapshots?limit=2', '/portfolio/holdings/NIFTYBEES/history?limit=2'):
        response = request(db, path)
        assert [row['snapshot_date'] for row in response.json()] == ['2026-10-05', '2026-10-06']


@pytest.mark.parametrize('limit', ['0', '-1', '3651', 'invalid'])
@pytest.mark.parametrize('path', ['/portfolio/snapshots', '/portfolio/holdings/NIFTYBEES/history'])
def test_history_limit_validation(db, path, limit):
    assert request(db, f'{path}?limit={limit}').status_code == 422


def test_daily_uniqueness_and_new_date(db, monkeypatch):
    add_holding(db)
    service.snapshot_today(db)
    monkeypatch.setattr(service, 'today', lambda: date(2026, 10, 7))
    service.snapshot_today(db)
    assert db.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 2
    assert db.scalar(select(func.count()).select_from(HoldingSnapshot)) == 2


def test_monthly_target_seed_idempotent_and_reads(db):
    first = seed_target(db)
    db.commit()
    first_id = first.id
    first.total_target = Decimal('1')
    db.commit()
    second = seed_target(db)
    db.commit()
    assert second.id == first_id and second.month == date(2026, 10, 1)
    assert db.scalar(select(func.count()).select_from(MonthlyTarget)) == 1
    for path in ('/portfolio/monthly-target', '/portfolio/monthly-target?month=2026-10'):
        response = request(db, path)
        assert response.status_code == 200
        values = response.json()
        assert values['month'] == '2026-10-01'
        assert Decimal(values['total_target']) == Decimal('15000')
        assert sum(Decimal(values[k]) for k in ('nifty_target', 'midcap_target', 'smallcap_target')) == Decimal('15000')
        assert 'progress' not in values
    assert request(db, '/portfolio/monthly-target?month=2026-11').status_code == 404
    assert MonthlyTarget(month=date(2026, 10, 18)).month == date(2026, 10, 1)


@pytest.mark.parametrize('month', ['2026-13', '2026-1', '2026-10-01', '0000-01', 'bad'])
def test_month_validation(db, month):
    assert request(db, f'/portfolio/monthly-target?month={month}').status_code == 422


def test_individual_equities_remain_other():
    for symbol in ('ETERNAL', 'FEDERALBNK', 'HDFCBANK', 'HINDUNILVR', 'KWIL', 'NYKAA', 'HDFCLIFE', 'INFY', 'KARURVYSYA', 'PNB'):
        assert zerodha.classify_instrument(symbol, "NSE") == Bucket.OTHER


def test_inactive_excluded_from_all_current_views_and_snapshots(db, monkeypatch):
    active = add_holding(db, 'CURRENT', bucket=Bucket.OTHER, invested='100', market='120')
    stale = add_holding(db, 'STALE', bucket=Bucket.NIFTY_50, invested='500', market='700')
    old_day = date(2026, 10, 5)
    monkeypatch.setattr(service, 'today', lambda: old_day)
    old_snapshot = service.snapshot_today(db)
    old_children = db.scalars(select(HoldingSnapshot).where(HoldingSnapshot.snapshot_date == old_day)).all()
    original_history = [(r.id, r.market_value, r.created_at) for r in old_children]
    monkeypatch.setattr(service, 'today', lambda: DAY)
    incorrect = service.snapshot_today(db)
    incorrect_id = incorrect.id
    stale.is_active = False
    db.commit()
    response = request(db, '/portfolio/holdings')
    assert [r['tradingsymbol'] for r in response.json()] == ['CURRENT']
    values = request(db, '/portfolio/summary').json()
    assert values['holding_count'] == 1
    assert Decimal(values['holdings_invested_value']) == Decimal('100')
    assert Decimal(values['holdings_market_value']) == Decimal('120')
    assert Decimal(values['total_pnl']) == Decimal('20')
    assert Decimal(values['allocation']['OTHER']) == Decimal('120')
    assert Decimal(values['allocation']['NIFTY_50']) == 0
    corrected = service.snapshot_today(db)
    assert corrected.id == incorrect_id
    assert corrected.holdings_invested_value == Decimal('100')
    assert corrected.holdings_market_value == Decimal('120')
    assert corrected.total_account_value == Decimal('5219.50')
    assert corrected.nifty_value == 0 and corrected.other_value == Decimal('120')
    assert db.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 2
    todays_children = db.scalars(select(HoldingSnapshot).where(HoldingSnapshot.snapshot_date == DAY)).all()
    assert [r.tradingsymbol for r in todays_children] == ['CURRENT']
    assert db.scalar(select(func.count()).select_from(Holding)) == 2
    assert db.get(Holding, stale.id).is_active is False
    db.refresh(old_snapshot)
    assert old_snapshot.holdings_market_value == Decimal('820')
    for row in old_children:
        db.refresh(row)
    assert [(r.id, r.market_value, r.created_at) for r in old_children] == original_history
    assert len(service.holding_history(db, 'STALE', 30)) == 1


def test_inactive_holding_never_generates_new_snapshot(db):
    stale = add_holding(db)
    stale.is_active = False
    db.commit()
    result = service.snapshot_today(db)
    assert result.holdings_market_value == 0
    assert result.total_account_value == Decimal('5099.50')
    assert db.scalar(select(func.count()).select_from(HoldingSnapshot)) == 0
