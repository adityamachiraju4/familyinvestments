"""MIS views use provider positions and cannot change delivery accounting."""
from decimal import Decimal
import pytest
from sqlalchemy import select
from test_activity import db, provider, TRADE, DAY, call, count
from app.models import InvestmentTransaction, Bucket, Holding
from app.portfolio import activity, intraday, service
from app.integrations.zerodha import buckets
from app.integrations.zerodha.exceptions import provider_error, credentials_error

POSITION = dict(tradingsymbol='NYKAA',exchange='NSE',product='MIS',quantity=2,
    overnight_quantity=0,buy_quantity=5,sell_quantity=3,buy_price='100',sell_price='110',
    buy_value='500',sell_value='330',realised='30',unrealised='20')


def mis_fills(provider):
    provider.orders=[]
    provider.trades=[{**TRADE,'tradingsymbol':'NYKAA','product':'MIS','quantity':5,'average_price':'100'},
        {**TRADE,'trade_id':'t2','order_id':'o2','tradingsymbol':'NYKAA','product':'MIS','transaction_type':'SELL','quantity':3,'average_price':'110'},
        {**TRADE,'trade_id':'delivery','order_id':'o3','quantity':2,'average_price':'280'}]


def positions(monkeypatch,provider,row=POSITION):
    monkeypatch.setattr(provider,'get_positions',lambda:{'net':[row],'day':[row]},raising=False)


def test_intraday_open_separation_idempotency_and_allocation(db,provider,monkeypatch):
    mis_fills(provider);positions(monkeypatch,provider)
    for _ in range(2): activity.refresh_portfolio(db)
    assert count(db,InvestmentTransaction)==3
    result=call(db,'/portfolio/intraday/today')
    assert result.status_code==200
    row=result.json()['positions'][0]
    assert row['product']=='MIS' and row['activity_type']=='INTRADAY'
    assert row['open_quantity']==2 and row['status']=='OPEN'
    assert Decimal(row['realised_pnl'])==30 and Decimal(row['unrealised_pnl'])==20
    assert row['buy_quantity']==5 and row['sell_quantity']==3 and row['fill_count']==2
    contribution=activity.contributions(db)
    assert contribution.recorded_buy_amount==560
    assert contribution.allocation[Bucket.NIFTY_50]==560
    assert sum(contribution.allocation.values())==560
    summary=service.calculate_summary(service.current_holdings(db,42),Decimal(0),None)
    assert summary.holdings_market_value==550 and sum(summary.allocation.values())==550
    assert 'NYKAA' not in [h.tradingsymbol for h in service.current_holdings(db,42)]
    assert len(activity.today_activity(db).executed)==3
    assert len(activity.today_activity(db).awaiting_holdings)==1


@pytest.mark.parametrize('quantity,status',[(0,'CLOSED'),(-2,'OPEN')])
def test_closed_and_short_provider_positions(db,provider,monkeypatch,quantity,status):
    row={**POSITION,'quantity':quantity,'sell_quantity':5 if quantity==0 else 7,'sell_value':'550' if quantity==0 else '770'}
    positions(monkeypatch,provider,row)
    result=intraday.today_intraday(db).positions[0]
    assert result.open_quantity==quantity and result.status==status


def test_cnc_is_not_intraday(db,provider,monkeypatch):
    positions(monkeypatch,provider,{**POSITION,'product':'CNC'})
    assert intraday.today_intraday(db).positions==[]


def test_missing_pnl_is_none_not_zero(db,provider,monkeypatch):
    positions(monkeypatch,provider,{**POSITION,'realised':None,'unrealised':None})
    result=intraday.today_intraday(db).positions[0]
    assert result.realised_pnl is None and result.unrealised_pnl is None


def test_provider_failure_preserves_fills_without_invented_pnl(db,provider,monkeypatch):
    mis_fills(provider);activity.refresh_portfolio(db)
    def fail():raise provider_error()
    monkeypatch.setattr(provider,'get_positions',fail,raising=False)
    view=intraday.today_intraday(db);row=view.positions[0]
    assert not view.positions_available and view.observed_at is None
    assert row.open_quantity==2 and row.status=='UNCONFIRMED'
    assert row.average_buy_price==100 and row.average_sell_price==110
    assert row.realised_pnl is None and row.unrealised_pnl is None


def test_position_credential_failure_requires_reconnect(db,provider,monkeypatch):
    def fail():raise credentials_error()
    monkeypatch.setattr(provider,'get_positions',fail,raising=False)
    assert call(db,'/portfolio/intraday/today').status_code==401


@pytest.mark.parametrize('change',[{'realised':'NaN'},{'buy_quantity':-1}])
def test_invalid_position_data_uses_empty_fallback(db,provider,monkeypatch,change):
    positions(monkeypatch,provider,{**POSITION,**change})
    response=call(db,'/portfolio/intraday/today')
    assert response.status_code==200
    assert response.json()['positions_available'] is False
    assert response.json()['positions']==[]


def test_registry_changes_current_classification_without_financial_mutation(db,provider,monkeypatch):
    provider.holdings=[dict(exchange='NSE',tradingsymbol='TEST_UNCLASSIFIED',instrument_token=123,quantity=5,t1_quantity=0,average_price='100',last_price='110')]
    activity.refresh_portfolio(db)
    holding=db.scalar(select(Holding));holding.bucket=Bucket.OTHER;db.commit()
    original=(holding.quantity,holding.average_price,holding.current_value,holding.bucket)
    assert call(db,'/portfolio/holdings').json()[0]['bucket']=='UNCLASSIFIED'
    values=call(db,'/portfolio/summary').json()
    assert Decimal(values['allocation']['UNCLASSIFIED'])==550
    entry=buckets.InstrumentClassification('TEST_UNCLASSIFIED',Bucket.LARGE_CAP,source='explicit_test_decision')
    monkeypatch.setattr(buckets,'ALIASES',{**buckets.ALIASES,('NSE','TEST_UNCLASSIFIED'):entry})
    assert call(db,'/portfolio/holdings').json()[0]['bucket']=='LARGE_CAP'
    values=call(db,'/portfolio/summary').json()
    assert Decimal(values['allocation']['LARGE_CAP'])==550
    db.refresh(holding)
    assert (holding.quantity,holding.average_price,holding.current_value,holding.bucket)==original


@pytest.mark.parametrize('change',[{'overnight_quantity':None},{'quantity':99}])
def test_unconfirmed_positions_do_not_present_pnl(db,provider,monkeypatch,change):
    positions(monkeypatch,provider,{**POSITION,**change})
    row=intraday.today_intraday(db).positions[0]
    assert row.status=='UNCONFIRMED' and row.open_quantity is None
    assert row.realised_pnl is None and row.unrealised_pnl is None


def test_positions_client_is_get_only(monkeypatch):
    from app.integrations.zerodha.client import KiteClient
    client=object.__new__(KiteClient);client._access_token='test-token'
    calls=[]
    monkeypatch.setattr(client,'_request',lambda method,path: calls.append((method,path)) or {'net':[],'day':[]})
    assert client.get_positions()=={'net':[],'day':[]}
    assert calls==[('GET','/portfolio/positions')]


def test_net_only_mis_position_remains_visible(db,provider,monkeypatch):
    monkeypatch.setattr(provider,'get_positions',lambda:{'net':[POSITION],'day':[]},raising=False)
    row=intraday.today_intraday(db).positions[0]
    assert row.status=='OPEN' and row.open_quantity==2 and row.realised_pnl==30


def test_legacy_classifications_flow_through_current_views_without_rewriting_history(db,provider,monkeypatch):
    from datetime import timedelta
    from app.models import HoldingSnapshot, PortfolioSnapshot
    symbols=['ETERNAL','HDFCBANK','HINDUNILVR','HDFCLIFE','INFY','PNB','FEDERALBNK','NYKAA','KARURVYSYA','KWIL']
    provider.holdings=[dict(exchange='NSE',tradingsymbol=symbol,instrument_token=index+1,
        quantity=1,t1_quantity=0,average_price='80',last_price='100') for index,symbol in enumerate(symbols)]
    provider.orders=[]
    provider.trades=[{**TRADE,'tradingsymbol':'FEDERALBNK','quantity':1,'average_price':'80'}]
    # Seed a preexisting historical snapshot using the prior registry configuration.
    original_aliases=buckets.ALIASES
    monkeypatch.setattr(buckets,'ALIASES',{})
    old_day=DAY-timedelta(days=1)
    provider.trades=[]
    monkeypatch.setattr(service,'today',lambda:old_day)
    activity.refresh_portfolio(db)
    historical=[(row.id,row.bucket,row.market_value) for row in db.scalars(select(HoldingSnapshot))]
    old_snapshot=db.scalar(select(PortfolioSnapshot))
    original_values=(old_snapshot.unclassified_value,old_snapshot.other_value,old_snapshot.midcap_value)
    monkeypatch.setattr(buckets,'ALIASES',original_aliases)
    monkeypatch.setattr(service,'today',lambda:DAY)
    # Current read fixes stale stored classifications immediately, without a sync.
    holdings=call(db,'/portfolio/holdings').json()
    assert all(row['bucket'] not in {'OTHER','UNCLASSIFIED'} for row in holdings)
    provider.trades=[{**TRADE,'tradingsymbol':'FEDERALBNK','quantity':1,'average_price':'80'}]
    activity.refresh_portfolio(db)
    values=call(db,'/portfolio/summary').json()
    assert Decimal(values['holdings_market_value'])==1000
    assert {key:Decimal(value) for key,value in values['allocation'].items()}=={
        'NIFTY_50':Decimal(0),'LARGE_CAP':Decimal(600),'MID_CAP':Decimal(200),
        'SMALL_CAP':Decimal(200),'OTHER':Decimal(0),'UNCLASSIFIED':Decimal(0)}
    assert sum(Decimal(value) for value in values['allocation'].values())==1000
    assert activity.today_activity(db).executed[0].bucket==Bucket.MID_CAP
    assert activity.contributions(db).allocation[Bucket.MID_CAP]==80
    assert [(row.id,row.bucket,row.market_value) for row in db.scalars(select(HoldingSnapshot).where(HoldingSnapshot.snapshot_date==old_day))]==historical
    db.refresh(old_snapshot)
    assert (old_snapshot.unclassified_value,old_snapshot.other_value,old_snapshot.midcap_value)==original_values
    current=db.scalars(select(HoldingSnapshot).where(HoldingSnapshot.snapshot_date==DAY)).all()
    assert all(row.bucket not in {Bucket.OTHER,Bucket.UNCLASSIFIED} for row in current)


@pytest.mark.parametrize('payload', [
    None, [], {}, {'net': [], 'day': [{}]}, {'net': {}, 'day': []}, {'net': [], 'day': [None]},
    {'net': [], 'day': [{**POSITION, 'realised': 'NaN'}]},
    {'net': [{**POSITION, 'buy_quantity': -1}], 'day': []},
    {'net': [POSITION, POSITION], 'day': []},
])
@pytest.mark.parametrize('with_fills', [True, False])
def test_provider_parsing_failures_return_200_fallback(db,provider,monkeypatch,payload,with_fills):
    if with_fills:
        mis_fills(provider);activity.refresh_portfolio(db)
    monkeypatch.setattr(provider,'get_positions',lambda:payload,raising=False)
    response=call(db,'/portfolio/intraday/today')
    assert response.status_code==200
    view=response.json()
    assert view['positions_available'] is False and view['observed_at'] is None
    assert len(view['positions'])==(1 if with_fills else 0)
    if with_fills:
        row=view['positions'][0]
        assert row['source']=='recorded_fills' and row['status']=='UNCONFIRMED'
        assert (row['buy_quantity'],row['sell_quantity'],row['open_quantity'])==(5,3,2)
        assert Decimal(row['buy_value'])==500 and Decimal(row['sell_value'])==330
        assert row['realised_pnl'] is None and row['unrealised_pnl'] is None


@pytest.mark.parametrize('with_fills',[True,False])
def test_kite_provider_error_returns_200_fallback(db,provider,monkeypatch,with_fills):
    if with_fills:
        mis_fills(provider);activity.refresh_portfolio(db)
    def fail():raise provider_error()
    monkeypatch.setattr(provider,'get_positions',fail,raising=False)
    response=call(db,'/portfolio/intraday/today')
    assert response.status_code==200 and response.json()['positions_available'] is False
    assert len(response.json()['positions'])==(1 if with_fills else 0)


@pytest.mark.parametrize('failure_point',['fills','client'])
def test_database_errors_are_not_swallowed(db,provider,monkeypatch,failure_point):
    from sqlalchemy.exc import OperationalError
    from app.integrations.zerodha import service as zerodha
    error=OperationalError(None,None,Exception('test database failure'))
    def fail(*args,**kwargs):raise error
    if failure_point=='fills':monkeypatch.setattr(db,'scalars',fail)
    else:monkeypatch.setattr(zerodha,'authenticated_client',fail)
    with pytest.raises(OperationalError):intraday.today_intraday(db)


@pytest.mark.parametrize('code',['database_unavailable','configuration_missing','dashboard_auth_required'])
def test_other_integration_errors_propagate(db,provider,monkeypatch,code):
    from app.integrations.zerodha.exceptions import IntegrationError
    error=IntegrationError(code,'Safe test failure')
    def fail():raise error
    monkeypatch.setattr(provider,'get_positions',fail,raising=False)
    with pytest.raises(IntegrationError) as raised:intraday.today_intraday(db)
    assert raised.value is error


def test_unrelated_programming_error_propagates(db,provider,monkeypatch):
    def fail():raise TypeError('programming error')
    monkeypatch.setattr(provider,'get_positions',fail,raising=False)
    with pytest.raises(TypeError):intraday.today_intraday(db)


def test_output_validation_errors_are_not_provider_failures(db,provider,monkeypatch):
    from pydantic import ValidationError
    positions(monkeypatch,provider)
    original=intraday.IntradayPosition
    def invalid_output(**kwargs):
        return original(**{**kwargs,'symbol':None})
    monkeypatch.setattr(intraday,'IntradayPosition',invalid_output)
    with pytest.raises(ValidationError):intraday.today_intraday(db)


@pytest.mark.parametrize('value,expected', [
    (Decimal('-3.8999999999999773'), Decimal('-3.9000')),
    (Decimal('3.8999999999999773'), Decimal('3.9000')),
    (0, Decimal('0.0000')), (17, Decimal('17.0000')),
    (Decimal('1.23456789123456789123456789'), Decimal('1.2346')),
])
def test_provider_precision_accepted_and_pnl_normalized(db,provider,monkeypatch,value,expected):
    positions(monkeypatch,provider,{**POSITION,'realised':value,'unrealised':value})
    raw=intraday.ProviderPosition.model_validate({**POSITION,'realised':value})
    assert raw.realised==Decimal(value)
    response=call(db,'/portfolio/intraday/today')
    assert response.status_code==200 and response.json()['positions_available'] is True
    row=response.json()['positions'][0]
    assert Decimal(row['realised_pnl'])==expected and Decimal(row['unrealised_pnl'])==expected


def test_live_nykaa_position_precision_and_provider_backed_pnl(db,provider,monkeypatch):
    live={**POSITION,'quantity':1,'buy_quantity':5,'sell_quantity':4,
          'buy_price':Decimal('344.2'),'sell_price':344,'buy_value':1721,'sell_value':1376,
          'realised':0,'unrealised':Decimal('-3.8999999999999773')}
    positions(monkeypatch,provider,live)
    response=call(db,'/portfolio/intraday/today')
    assert response.status_code==200 and response.json()['positions_available'] is True
    row=response.json()['positions'][0]
    assert (row['product'],row['buy_quantity'],row['sell_quantity'],row['open_quantity'],row['status'])==('MIS',5,4,1,'OPEN')
    assert Decimal(row['buy_value'])==1721 and Decimal(row['sell_value'])==1376
    # Preserve provider realised zero; do not substitute a buy/sell spread estimate.
    assert Decimal(row['realised_pnl'])==0 and Decimal(row['unrealised_pnl'])==Decimal('-3.9000')
    assert row['source']=='provider_positions'


@pytest.mark.parametrize('field',['realised','unrealised','buy_price','sell_price','buy_value','sell_value'])
@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','not-a-number','1e100','1e16',{}])
def test_invalid_numeric_provider_values_rejected_with_safe_fallback(db,provider,monkeypatch,field,value):
    from pydantic import ValidationError
    payload={**POSITION,field:value}
    with pytest.raises(ValidationError):intraday.ProviderPosition.model_validate(payload)
    positions(monkeypatch,provider,payload)
    response=call(db,'/portfolio/intraday/today')
    assert response.status_code==200 and response.json()['positions_available'] is False
    assert response.json()['positions']==[]


def test_provider_turnover_precision_is_preserved():
    precise=Decimal('1721.123456789123456789')
    row=intraday.ProviderPosition.model_validate({**POSITION,'buy_value':precise,'buy_price':precise})
    assert row.buy_value==precise and row.buy_price==precise


def test_negative_absurd_pnl_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        intraday.ProviderPosition.model_validate({**POSITION,'unrealised':Decimal('-1e16')})
