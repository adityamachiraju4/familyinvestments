"""Mocked Kite HTTP and isolated persistence; never contact the live provider."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import importlib.util
import logging
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock

from cryptography.fernet import Fernet
import httpx
from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.config import settings
from app.main import app
from app.models import Holding, ZerodhaAccount, ZerodhaCredential, Bucket
from app.integrations.zerodha import crypto, service, client as client_module
from app.integrations.zerodha.client import KiteClient
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.routes import CallbackLogFilter, integration_db

NOW = datetime.now(timezone.utc)
TOKEN = 'testaccesstoken'
RAW = {'exchange': 'NSE', 'tradingsymbol': 'NIFTYBEES', 'instrument_token': 123,
       'quantity': 3, 't1_quantity': 1, 'average_price': '0.10', 'last_price': '0.30'}

@pytest.fixture(autouse=True)
def config(monkeypatch):
    for field, value in {'ZERODHA_API_KEY': 'testapikey', 'ZERODHA_API_SECRET': SecretStr('testapisecret'),
                         'ZERODHA_REDIRECT_URL': 'http://127.0.0.1:8000/integrations/zerodha/callback',
                         'TOKEN_ENCRYPTION_KEY': SecretStr(Fernet.generate_key().decode())}.items():
        monkeypatch.setattr(settings, field, value)
    monkeypatch.setattr(KiteClient, '_request', lambda *a, **kw: pytest.fail('Unexpected provider request'))

@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def configure(connection, record):
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))
        connection.execute('PRAGMA foreign_keys=ON')
    for model in (ZerodhaAccount, ZerodhaCredential, Holding):
        model.__table__.create(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(ZerodhaAccount(client_id='LOCAL_DEV', display_name='Primary Zerodha Account'))
        session.commit()
        yield session
    engine.dispose()

def api_call(path, method='GET', db=None):
    async def run():
        if db is not None:
            app.dependency_overrides[integration_db] = lambda: db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000') as client:
                return await client.request(method, path)
        finally:
            app.dependency_overrides.clear()
    return asyncio.run(run())

def store_token(db, expires=NOW + timedelta(hours=12)):
    db.add(ZerodhaCredential(account_id=service.single_account(db).id, encrypted_access_token=crypto.encrypt_token(TOKEN), token_created_at=NOW, token_expires_at=expires))
    db.commit()

def test_encryption_round_trip_and_tampering():
    encrypted = crypto.encrypt_token(TOKEN)
    assert encrypted != TOKEN and TOKEN not in encrypted
    assert crypto.decrypt_token(encrypted) == TOKEN
    with pytest.raises(IntegrationError):
        crypto.decrypt_token(encrypted[:-4] + 'aaaa')

@pytest.mark.parametrize('key', [None, SecretStr('invalid')])
def test_missing_or_invalid_encryption_key(monkeypatch, key):
    monkeypatch.setattr(settings, 'TOKEN_ENCRYPTION_KEY', key)
    with pytest.raises(IntegrationError) as exc:
        crypto.encrypt_token(TOKEN)
    assert exc.value.code == 'configuration_missing'

def test_login_url_and_cookie():
    response = api_call('/integrations/zerodha/login')
    assert response.status_code == 200
    url = urlsplit(response.json()['login_url'])
    assert (url.scheme, url.netloc, url.path) == ('https', 'kite.zerodha.com', '/connect/login')
    params = parse_qs(url.query)
    assert params['api_key'] == ['testapikey'] and params['v'] == ['3']
    assert parse_qs(params['redirect_params'][0])['state']
    assert 'testapisecret' not in response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    assert response.headers['cache-control'] == 'no-store'

@pytest.mark.parametrize('field', ['ZERODHA_API_KEY', 'ZERODHA_API_SECRET', 'ZERODHA_REDIRECT_URL', 'TOKEN_ENCRYPTION_KEY'])
def test_missing_config_fails_closed(monkeypatch, field):
    monkeypatch.setattr(settings, field, None)
    response = api_call('/integrations/zerodha/login')
    assert response.status_code == 503
    assert response.json()['error'] == 'configuration_missing'

def callback_flow(db, monkeypatch, user_id='AB1234'):
    monkeypatch.setattr(KiteClient, 'exchange_token', lambda self, token: {'access_token': TOKEN, 'user_id': user_id})
    async def run():
        app.dependency_overrides[integration_db] = lambda: db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000') as client:
                login = await client.get('/integrations/zerodha/login')
                params = parse_qs(urlsplit(login.json()['login_url']).query)
                state = parse_qs(params['redirect_params'][0])['state'][0]
                return await client.get('/integrations/zerodha/callback', params={'request_token': 'testrequesttoken', 'state': state})
        finally:
            app.dependency_overrides.clear()
    return asyncio.run(run())

def test_callback_encrypted_upsert_and_status(db, monkeypatch):
    for _ in range(2):
        response = callback_flow(db, monkeypatch)
        assert response.status_code == 200 and response.json() == {'status': 'connected'}
        assert TOKEN not in response.text and 'testapisecret' not in response.text
    assert db.scalar(select(func.count()).select_from(ZerodhaCredential)) == 1
    stored = db.scalar(select(ZerodhaCredential))
    db.refresh(stored)
    assert stored.encrypted_access_token != TOKEN
    assert crypto.decrypt_token(stored.encrypted_access_token) == TOKEN
    assert stored.token_expires_at > stored.token_created_at
    status = api_call('/integrations/zerodha/status', db=db)
    assert set(status.json()) == {'connection_status', 'last_authenticated_at', 'last_sync_at', 'credentials_present'}
    assert status.json()['connection_status'] == 'connected' and status.json()['credentials_present']
    assert service.single_account(db).client_id == 'AB1234'

def test_callback_rejects_account_mismatch(db, monkeypatch):
    service.single_account(db).client_id = 'EXPECTED'
    db.commit()
    assert callback_flow(db, monkeypatch, 'OTHER').status_code == 409
    assert db.scalar(select(func.count()).select_from(ZerodhaCredential)) == 0

def test_callback_rejects_missing_state(db):
    response = api_call('/integrations/zerodha/callback?request_token=testrequesttoken', db=db)
    assert response.status_code == 400 and 'testrequesttoken' not in response.text

@pytest.mark.parametrize('symbol,bucket', [('NIFTYBEES', Bucket.NIFTY_50), ('MIDCAPETF', Bucket.MID_CAP), ('UNKNOWN', Bucket.OTHER)])
def test_bucket_mapping(symbol, bucket):
    assert service.bucket_for(symbol) == bucket

def test_decimal_normalization_and_zero_cost():
    values = service.normalize_holding(RAW, 22, NOW)
    for key, expected in {'invested_value': '0.3000', 'current_value': '0.9000', 'unrealised_pnl': '0.6000', 'unrealised_pnl_percent': '200.000000'}.items():
        assert values[key] == Decimal(expected)
    assert values['bucket'] == Bucket.NIFTY_50 and values['account_id'] == 22 and values['t1_quantity'] == 1
    assert service.normalize_holding({**RAW, 'average_price': 0}, 22, NOW)['unrealised_pnl_percent'] == 0

@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1'])
def test_invalid_prices_sanitized(value):
    with pytest.raises(IntegrationError) as exc:
        service.normalize_holding({**RAW, 'average_price': value}, 1, NOW)
    assert exc.value.code == 'provider_error'

def test_holdings_upsert_preserves_absent_rows(db, monkeypatch):
    store_token(db)
    monkeypatch.setattr(KiteClient, 'get_holdings', lambda self: [RAW])
    assert api_call('/integrations/zerodha/sync/holdings', 'POST', db).json()['holdings_synced'] == 1
    original = db.scalar(select(Holding))
    original_id = original.id
    monkeypatch.setattr(KiteClient, 'get_holdings', lambda self: [{**RAW, 'quantity': 4}])
    assert service.sync_holdings(db) == 1
    db.refresh(original)
    assert original.id == original_id and original.quantity == 4
    assert db.scalar(select(func.count()).select_from(Holding)) == 1
    assert service.single_account(db).last_sync_at is not None
    monkeypatch.setattr(KiteClient, 'get_holdings', lambda self: [])
    assert service.sync_holdings(db) == 0
    assert db.scalar(select(func.count()).select_from(Holding)) == 1
    response = api_call('/portfolio/holdings', db=db)
    assert response.status_code == 200
    row = response.json()[0]
    assert row['quantity'] == 4 and row['bucket'] == 'NIFTY_50' and row['invested_value'] == '0.4000'
    assert 'account_id' not in row and 'access_token' not in response.text

def test_no_partial_sync_on_invalid_payload(db, monkeypatch):
    store_token(db)
    monkeypatch.setattr(KiteClient, 'get_holdings', lambda self: [RAW, {'invalid': True}])
    assert api_call('/integrations/zerodha/sync/holdings', 'POST', db).status_code == 502
    assert db.scalar(select(func.count()).select_from(Holding)) == 0
    assert service.single_account(db).last_sync_at is None

def test_funds_normalized(db, monkeypatch):
    store_token(db)
    monkeypatch.setattr(KiteClient, 'get_margins', lambda self: {'available': {'cash': Decimal('12.34'), 'opening_balance': '20', 'live_balance': '12.34'}, 'net': '10', 'secret': TOKEN})
    response = api_call('/portfolio/funds', db=db)
    assert response.status_code == 200
    assert response.json() == {'available_cash': '12.34', 'opening_balance': '20', 'live_balance': '12.34', 'net': '10'}
    assert TOKEN not in response.text

@pytest.mark.parametrize('path,method', [('/portfolio/funds', 'GET'), ('/integrations/zerodha/sync/holdings', 'POST')])
def test_missing_stored_token(db, path, method):
    assert api_call(path, method, db).status_code == 401

def test_expired_stored_token(db):
    store_token(db, NOW - timedelta(hours=1))
    with pytest.raises(IntegrationError) as exc:
        service.authenticated_client(db, service.single_account(db))
    assert exc.value.code == 'credentials_invalid'

@pytest.mark.parametrize('count', [0, 2])
def test_account_selection_fails_for_zero_or_multiple(db, count):
    if count == 0:
        db.delete(service.single_account(db))
    else:
        db.add(ZerodhaAccount(client_id='OTHER', display_name='Other'))
    db.commit()
    assert api_call('/integrations/zerodha/status', db=db).status_code == 409

def test_database_failure_sanitized(monkeypatch):
    monkeypatch.setattr(database, 'SessionLocal', MagicMock(side_effect=OperationalError(None, None, Exception('postgresql://user:secret@private/db'))))
    response = api_call('/integrations/zerodha/status')
    assert response.status_code == 503 and 'private' not in response.text and 'secret' not in response.text

def test_callback_access_log_is_redacted():
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d', ('127.0.0.1', 'GET', '/integrations/zerodha/callback?request_token=private&state=x', '1.1', 200), None)
    CallbackLogFilter().filter(record)
    assert 'request_token' not in record.getMessage() and 'private' not in record.getMessage()

def test_provider_transport_patterns_and_sanitization(monkeypatch):
    spec = importlib.util.spec_from_file_location('client_test_copy', client_module.__file__)
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    original_client = httpx.Client
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == '/session/token':
            return httpx.Response(200, json={'status': 'success', 'data': {'access_token': TOKEN, 'user_id': 'AB1234'}})
        return httpx.Response(200, content=b'{"status":"success","data":{"available":{"cash":0.1}}}')
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw))
    copy.KiteClient().exchange_token('requesttoken')
    params = parse_qs(requests[0].content.decode())
    assert params['checksum'] == [hashlib.sha256(b'testapikeyrequesttokentestapisecret').hexdigest()]
    assert 'testapisecret' not in requests[0].content.decode()
    assert requests[0].method == 'POST' and requests[0].url.path == '/session/token'
    assert copy.KiteClient(TOKEN).get_margins()['available']['cash'] == Decimal('0.1')
    assert requests[1].headers['Authorization'] == 'token testapikey:testaccesstoken'
    assert requests[1].headers['X-Kite-Version'] == '3'
    copy.KiteClient(TOKEN).get_holdings()
    assert requests[2].url.path == '/portfolio/holdings' and requests[2].method == 'GET'
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_client(transport=httpx.MockTransport(lambda req: httpx.Response(500, json={'message': TOKEN + ' testapisecret'})), **kw))
    with pytest.raises(IntegrationError) as exc:
        copy.KiteClient(TOKEN).get_holdings()
    assert str(exc.value) == 'Zerodha request failed'

def test_routes_have_no_order_mutations():
    paths = app.openapi()['paths']
    assert '/portfolio/holdings' in paths and '/portfolio/funds' in paths
    assert not any('order' in path for path in paths)
    assert {(path, method) for path, methods in paths.items() for method in methods if method in {'post', 'put', 'patch', 'delete'}} == {('/integrations/zerodha/sync/holdings', 'post'), ('/portfolio/snapshots/today', 'post')}

@pytest.mark.parametrize('status,payload,code', [
    (401, {'message': TOKEN}, 'credentials_invalid'),
    (403, {'message': 'testapisecret'}, 'credentials_invalid'),
    (429, {'message': TOKEN}, 'provider_error'),
    (200, {'status': 'error', 'error_type': 'TokenException', 'message': TOKEN}, 'credentials_invalid'),
    (200, {'status': 'error', 'message': TOKEN}, 'provider_error'),
    (200, ['invalid', TOKEN], 'provider_error'),
])
def test_provider_api_errors_sanitized(monkeypatch, status, payload, code):
    spec = importlib.util.spec_from_file_location('client_error_copy', client_module.__file__)
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    original_client = httpx.Client
    transport = httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_client(transport=transport, **kw))
    with pytest.raises(IntegrationError) as exc:
        copy.KiteClient(TOKEN).get_holdings()
    assert exc.value.code == code
    assert TOKEN not in str(exc.value) and 'testapisecret' not in str(exc.value)


def test_provider_timeout_sanitized(monkeypatch):
    spec = importlib.util.spec_from_file_location('client_timeout_copy', client_module.__file__)
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    original_client = httpx.Client
    def timeout(request):
        raise httpx.ReadTimeout('private ' + TOKEN, request=request)
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_client(transport=httpx.MockTransport(timeout), **kw))
    with pytest.raises(IntegrationError) as exc:
        copy.KiteClient(TOKEN).get_margins()
    assert str(exc.value) == 'Zerodha request failed'


def test_status_disconnected_without_credentials(db):
    response = api_call('/integrations/zerodha/status', db=db)
    assert response.json() == {'connection_status': 'disconnected', 'last_authenticated_at': None, 'last_sync_at': None, 'credentials_present': False}


def test_duplicate_holdings_rejected_before_writes(db, monkeypatch):
    store_token(db)
    monkeypatch.setattr(KiteClient, 'get_holdings', lambda self: [RAW, RAW])
    assert api_call('/integrations/zerodha/sync/holdings', 'POST', db).status_code == 502
    assert db.scalar(select(func.count()).select_from(Holding)) == 0


def test_missing_database_fails_safely(monkeypatch):
    monkeypatch.setattr(database, 'SessionLocal', None)
    response = api_call('/integrations/zerodha/status')
    assert response.status_code == 503 and response.json()['error'] == 'database_unavailable'


def test_funds_provider_failure_is_safe_http_response(db, monkeypatch):
    store_token(db)
    def fail(self):
        from app.integrations.zerodha.exceptions import provider_error
        raise provider_error()
    monkeypatch.setattr(KiteClient, 'get_margins', fail)
    response = api_call('/portfolio/funds', db=db)
    assert response.status_code == 502
    assert response.json() == {'error': 'provider_error', 'message': 'Zerodha request failed'}
