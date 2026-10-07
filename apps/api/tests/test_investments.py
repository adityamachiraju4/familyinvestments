from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models.mutual_fund import MutualFundAccount, MutualFundScheme, SIP, MutualFundHolding, MutualFundTransaction
from app.investments.calculations import future_value, rounded, xirr, SCENARIOS, validate_rate, DISCLOSURE
from app.investments import service
from app.investments.imports import import_transactions

@pytest.fixture
def db(monkeypatch):
    from sqlalchemy.pool import StaticPool
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[m.__table__ for m in (MutualFundAccount, MutualFundScheme, SIP, MutualFundHolding, MutualFundTransaction)])
    monkeypatch.setattr(service,'today',lambda: date(2026,10,7))
    with Session(engine) as db:
        db.add(MutualFundAccount(id=1,display_name='Test household member'))
        db.add(MutualFundScheme(id=1,account_id=1,scheme_key='verified-key',scheme_name='Test fund',history_complete=True))
        db.flush()
        yield db
    engine.dispose()

def sip(db,status='ACTIVE',amount='1000'):
    row = SIP(scheme_id=1,source='MANUAL',monthly_amount=D(amount),sip_day=7,start_date=date(2025,1,1),status=status)
    db.add(row); db.flush()
    return row

@pytest.mark.parametrize('years,expected',[(1,'12565.57'),(5,'77437.07'),(10,'204844.98')])
def test_horizons(years,expected):
    assert rounded(future_value(D(0),[D(1000)]*(years*12),D(10))['projected_value']) == D(expected)

@pytest.mark.parametrize('status',['ACTIVE','PAUSED','STOPPED'])
def test_status(db,status):
    sip(db,status)
    summary = service.summary(db)
    assert summary['monthly_sip'] == (D(1000) if status=='ACTIVE' else 0)
    assert service.projections(db,D(0))['combined']['one_year']['future_contributions'] == (D(12000) if status=='ACTIVE' else 0)

def test_decimal_zero_and_corpus():
    p=future_value(D('0.1'),[D('0.2')]*12,D(0))
    assert p['projected_value']==D('2.5') and p['projected_growth']==0
    assert rounded(future_value(D(1000),[D(0)]*12,D(12))['projected_value'])==D('1126.83')

@pytest.mark.parametrize('name,rate',SCENARIOS)
def test_scenarios(name,rate):
    p=future_value(D(500),[D(1000)]*60,rate)
    assert p['future_contributions']==60000
    assert abs(p['projected_value']-(500+p['future_contributions']+p['projected_growth'])) < D('.00000001')

@pytest.mark.parametrize('rate',[D(-1),D(31),D('NaN'),D('Infinity'),10.0])
def test_invalid_rate(rate):
    with pytest.raises(ValueError): validate_rate(rate)

def test_combined_no_double_count(db):
    sip(db);sip(db,amount='2000')
    db.add(MutualFundHolding(scheme_id=1,source='MANUAL',current_value=D(5000),invested_amount=D(4000),valuation_date=date(2026,10,7)))
    db.flush()
    p=service.projections(db,D(10))
    for key in ['one_year','five_years','ten_years']:
        assert abs(sum(s['projections'][key]['projected_value'] for s in p['sips'])-p['combined'][key]['projected_value']) < D('.00000001')
    assert service.summary(db)['current_value']==5000
    assert service.summary(db)['gain_loss']==1000
    assert 'not guaranteed returns' in DISCLOSURE

def test_dates_and_missing_corpus(db):
    row=sip(db);row.end_date=date(2027,1,7)
    p=service.projections(db,D(0))
    assert not p['corpus_complete']
    assert p['combined']['one_year']['future_contributions']==3000
    assert service.summary(db)['current_value'] is None

def test_import_idempotency_and_contributions(db):
    row=sip(db)
    data=dict(scheme_id=1,sip_id=row.id,source='CAS',import_key='event-1',transaction_date=date(2026,10,1),transaction_type='SIP',amount=D(1000),status='CONFIRMED')
    provider=SimpleNamespace(transactions=lambda: [data])
    assert import_transactions(db,provider)==1
    assert import_transactions(db,provider)==0
    assert service.monthly_contributions(db)==1000
    for kind in ['REDEMPTION','SWITCH_IN','SWITCH_OUT','DIVIDEND']:
        import_transactions(db,SimpleNamespace(transactions=lambda: [{**data,'import_key':kind,'transaction_type':kind}]))
    assert service.monthly_contributions(db)==1000
    with pytest.raises(ValueError):
        import_transactions(db,SimpleNamespace(transactions=lambda: [{**data,'amount':D(2000)}]))

def test_xirr():
    assert xirr([(date(2025,1,1),D(-1000)),(date(2026,1,1),D(1100))])==D(10)
    assert xirr([]) is None
    assert xirr([(date(2025,1,1),D(-1000))]) is None
    assert xirr([(date(2025,1,1),D(-1000)),(date(2026,1,1),D(1100)),(date(2027,1,1),D(-1))]) is None

def test_actual_history_gate(db):
    scheme=db.get(MutualFundScheme,1)
    holding=MutualFundHolding(current_value=D(1100),invested_amount=D(1000),valuation_date=date(2026,1,1))
    transaction=MutualFundTransaction(transaction_date=date(2025,1,1),transaction_type='SIP',amount=D(1000))
    assert service.actual(scheme,holding,[transaction])['xirr']==10
    scheme.history_complete=False
    assert service.actual(scheme,holding,[transaction])['xirr'] is None

def test_family_composition():
    assert service.family_composition(D(100),D(20),D(30))['long_term_wealth']==150
    assert service.family_composition(D(100),None,D(30))['long_term_wealth'] is None

@pytest.mark.parametrize('amount',[1000.0,D('NaN'),D(-1),D(0)])
def test_invalid_import_money(db,amount):
    provider=SimpleNamespace(transactions=lambda:[dict(scheme_id=1,source='CAS',import_key='x',transaction_date=date(2026,1,1),transaction_type='SIP',amount=amount)])
    with pytest.raises(ValueError): import_transactions(db,provider)

def test_read_routes_and_rates(db):
    import asyncio, httpx
    from app.main import app
    from app.auth.service import require_access
    from app.integrations.zerodha.routes import integration_db
    async def call(path,method='GET'):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            return await client.request(method,path)
    app.dependency_overrides[integration_db]=lambda:db
    app.dependency_overrides[require_access]=lambda:None
    try:
        for path in ['/investments/sips','/investments/mutual-funds/summary','/investments/sips/projections']:
            response=asyncio.run(call(path))
            assert response.status_code==200
            assert response.headers['cache-control']=='no-store'
            assert asyncio.run(call(path,'POST')).status_code==405
        for rate in ['-1','31','NaN','Infinity','abc']:
            assert asyncio.run(call('/investments/sips/projections?annual_return='+rate)).status_code==422
    finally: app.dependency_overrides.clear()

def test_new_migration_matches_models(monkeypatch):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import MetaData
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import postgresql
    path=Path(__file__).parents[1]/'alembic/versions/0007_mutual_funds.py'
    spec=importlib.util.spec_from_file_location('mf_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    tables={}
    def capture(name,*columns):
        from sqlalchemy import Table
        tables[name]=Table(name,Base.metadata.__class__(naming_convention=Base.metadata.naming_convention),*columns)
    monkeypatch.setattr(migration.op,'create_table',capture)
    migration.upgrade()
    # Copy to one metadata graph so foreign keys resolve, including account dependencies.
    metadata=MetaData(naming_convention=Base.metadata.naming_convention)
    for table in tables.values(): table.to_metadata(metadata)
    for name,table in metadata.tables.items():
        def ddl(t):
            return sorted(line.strip().rstrip(',') for line in str(CreateTable(t).compile(dialect=postgresql.dialect())).splitlines() if line.strip())
        assert ddl(table)==ddl(Base.metadata.tables[name])
