"""Real auth/CSRF with isolated storage and fixed test-only credentials."""
from datetime import timedelta
from unittest.mock import MagicMock
import asyncio
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from app.main import app, lifespan
from app.auth import service
from app.auth.passwords import password_hash
from app.config import settings, Settings
from app.models.auth import DashboardSession, LoginAttempt
from app.integrations.zerodha.routes import integration_db
from app.integrations.zerodha import service as zerodha

ORIGIN = 'http://127.0.0.1:5173'
PASSWORD = 'test-only-long-password'

@pytest.fixture(scope='module')
def hashed():
    return password_hash(PASSWORD)

@pytest.fixture
def auth(monkeypatch, hashed):
    for key,value in dict(APP_ENV='development', FRONTEND_ORIGIN=None, DASHBOARD_USERNAME='household', DASHBOARD_PASSWORD_HASH=SecretStr(hashed), SESSION_SECRET=SecretStr('test-session-secret-at-least-32-bytes'), SESSION_TTL_SECONDS=3600).items():
        monkeypatch.setattr(settings,key,value)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    from app.models import ZerodhaAccount, ZerodhaLoginState
    @event.listens_for(engine, 'connect')
    def configure(connection, record):
        connection.create_function('now', 0, lambda: service.now().isoformat(' '))
        connection.execute('PRAGMA foreign_keys=ON')
    for model in (DashboardSession, LoginAttempt, ZerodhaAccount, ZerodhaLoginState):
        model.__table__.create(engine)
    from app import database
    monkeypatch.setattr(database, 'SessionLocal', lambda: Session(engine, expire_on_commit=False))
    with Session(engine,expire_on_commit=False) as db:
        db.add(ZerodhaAccount(client_id='LOCAL_DEV', display_name='Test account')); db.commit()
        app.dependency_overrides[service.auth_db]=lambda: db
        app.dependency_overrides[integration_db]=lambda: db
        with TestClient(app) as client:
            yield client,db
        app.dependency_overrides.clear()
    engine.dispose()


def login(client, username='household', password=PASSWORD):
    return client.post('/auth/login',json={'username':username,'password':password},headers={'Origin':ORIGIN})


def test_health_public(auth,monkeypatch):
    from app import database
    monkeypatch.setattr(database,'engine',None)
    client,_=auth
    assert client.get('/health').status_code==200
    assert client.get('/health/db').json()['status']=='unconfigured'
    assert client.get('/auth/session').json()['authenticated'] is False


@pytest.mark.parametrize('path,method',[('/portfolio/holdings','GET'),('/portfolio/summary','GET'),('/portfolio/activity/today','GET'),('/portfolio/refresh','POST'),('/integrations/zerodha/status','GET'),('/integrations/zerodha/login','GET'),('/integrations/zerodha/sync/holdings','POST')])
def test_private_routes_reject_unauthenticated(auth,path,method):
    response=auth[0].request(method,path)
    assert response.status_code==401
    assert response.json()['detail']['error']=='dashboard_auth_required'


def test_valid_login_session_logout_revokes_replayed_cookie(auth):
    client,db=auth
    response=login(client)
    assert response.status_code==200 and response.json()['authenticated']
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie']
    cookie=client.cookies.get(service.cookie_name())
    csrf=response.json()['csrf_token']
    assert client.get('/auth/session').json()['authenticated']
    assert client.post('/auth/logout',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}).status_code==200
    client.cookies.set(service.cookie_name(),cookie)
    assert not client.get('/auth/session').json()['authenticated']
    assert db.scalar(select(func.count()).select_from(DashboardSession))==0


@pytest.mark.parametrize('username,password',[('wrong',PASSWORD),('household','wrong')])
def test_invalid_credentials_generic(auth,username,password):
    response=login(auth[0],username,password)
    assert response.status_code==401 and response.json()['detail']=='Invalid username or password'
    assert password not in response.text


def test_expired_and_tampered_session(auth):
    client,db=auth
    login(client)
    value=client.cookies.get(service.cookie_name())
    row=db.scalar(select(DashboardSession));row.expires_at=service.now()-timedelta(seconds=1);db.commit()
    assert not client.get('/auth/session').json()['authenticated']
    client.cookies.clear();client.cookies.set(service.cookie_name(),value[:-1]+'x')
    assert client.get('/portfolio/holdings').status_code==401
    client.cookies.clear();client.cookies.set(service.cookie_name(),'malformed')
    assert not client.get('/auth/session').json()['authenticated']


def test_password_rotation_revokes_session(auth,monkeypatch,hashed):
    client,_=auth;login(client)
    monkeypatch.setattr(settings,'DASHBOARD_USERNAME','changed')
    assert not client.get('/auth/session').json()['authenticated']


def test_csrf_and_origin_required(auth):
    client,_=auth
    assert client.post('/auth/login',json={'username':'household','password':PASSWORD}).status_code==403
    csrf=login(client).json()['csrf_token']
    for headers in ({'Origin':ORIGIN},{'Origin':'https://attacker.example','X-CSRF-Token':csrf},{'X-CSRF-Token':csrf}):
        assert client.post('/auth/logout',headers=headers).status_code==403
    assert client.get('/integrations/zerodha/login',headers={'Origin':ORIGIN}).status_code==403


def test_rate_limit_persists_across_clients_and_expires(auth,monkeypatch):
    client,db=auth
    # Avoid redundant expensive hashing; password verification is independently tested.
    monkeypatch.setattr(service,'verify',lambda *args:False)
    for _ in range(10):assert login(client,password='wrong').status_code==401
    assert login(client).status_code==429
    with TestClient(app) as another:
        assert login(another).status_code==429
    for row in db.scalars(select(LoginAttempt)):row.window_started_at=service.now()-timedelta(seconds=901)
    db.commit()
    assert login(client,password='wrong').status_code==401


def test_production_missing_config_fails_startup(monkeypatch):
    with pytest.raises(RuntimeError,match='authentication configuration'):
        service.validate_config(Settings(_env_file=None,APP_ENV='production'))
    monkeypatch.setattr(settings, 'APP_ENV', 'production')
    monkeypatch.setattr(settings, 'FRONTEND_ORIGIN', 'https://dashboard.example.com')
    monkeypatch.setattr(settings, 'DASHBOARD_PASSWORD_HASH', None)
    with pytest.raises(RuntimeError,match='authentication configuration'):
        with TestClient(app):
            pass


def test_production_cookie_flags(auth,monkeypatch):
    client,_=auth
    monkeypatch.setattr(settings,'APP_ENV','production');monkeypatch.setattr(settings,'FRONTEND_ORIGIN',ORIGIN)
    # Check flags independently of the HTTPS-only production origin validation.
    options=service.cookie_options()
    assert options['secure'] and options['httponly'] and options['samesite']=='none'
    assert service.cookie_name().startswith('__Host-') and 'domain' not in options


def test_login_validation_never_echoes_password(auth):
    response=auth[0].post('/auth/login',json={'username':'household','password':'private'*200},headers={'Origin':ORIGIN})
    assert response.status_code==400 and 'private' not in response.text


def test_zerodha_callback_bound_to_dashboard_session(auth,monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    client,db=auth
    for key,value in dict(ZERODHA_API_KEY='testapikey',ZERODHA_API_SECRET=SecretStr('testsecret'),ZERODHA_REDIRECT_URL='http://testserver/integrations/zerodha/callback',TOKEN_ENCRYPTION_KEY=SecretStr(Fernet.generate_key().decode())).items():monkeypatch.setattr(settings,key,value)
    # Existing callback permits HTTP loopback only; use a loopback test host.
    monkeypatch.setattr(settings,'ZERODHA_REDIRECT_URL','http://127.0.0.1/integrations/zerodha/callback')
    import httpx
    client.base_url=httpx.URL('http://127.0.0.1')
    csrf=login(client).json()['csrf_token']
    response=client.get('/integrations/zerodha/login',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
    assert response.status_code==200
    state=parse_qs(parse_qs(urlsplit(response.json()['login_url']).query)['redirect_params'][0])['state'][0]
    connected=MagicMock();monkeypatch.setattr(zerodha,'connect',connected)
    callback='/integrations/zerodha/callback?request_token=testrequest&state='+state
    client.cookies.clear()  # Top-level callback may not receive partitioned household cookies.
    assert client.get(callback,follow_redirects=False).headers['location'].endswith('?zerodha=connected')
    connected.assert_called_once()
    # Reusing a valid old brokerage state with a new dashboard session is rejected.
    csrf=login(client).json()['csrf_token']
    client.cookies.set('zerodha_login_state',state)
    assert client.get(callback,follow_redirects=False).headers['location'].endswith('?zerodha=connect_failed')


def test_login_logs_and_database_do_not_store_password_or_cookie(auth,caplog):
    client,db=auth
    response=login(client)
    assert response.status_code==200
    cookie=client.cookies.get(service.cookie_name())
    assert PASSWORD not in caplog.text and cookie not in caplog.text
    row=db.scalar(select(DashboardSession))
    assert row.token_hash not in cookie and len(row.token_hash)==64
    assert set(DashboardSession.__table__.columns.keys())=={'id','token_hash','credential_version','expires_at'}
    assert set(LoginAttempt.__table__.columns.keys())=={'id','key_hash','window_started_at','attempts'}


def test_all_private_routes_carry_access_dependency():
    from fastapi.routing import APIRoute
    for route in app.routes:
        if isinstance(route,APIRoute) and route.path != '/integrations/zerodha/callback' and route.path.startswith(('/portfolio/','/integrations/zerodha/')):
            assert any(dependency.call is service.require_access for dependency in route.dependant.dependencies)


def test_household_limit_blocks_rotating_addresses(auth,monkeypatch):
    _,db=auth
    monkeypatch.setattr(service,'verify',lambda *args:False)
    for index in range(30):
        with TestClient(app,client=(f'192.0.2.{index+1}',1234)) as client:
            assert login(client,password='wrong').status_code==401
    count_before=db.scalar(select(func.count()).select_from(LoginAttempt))
    with TestClient(app,client=('192.0.2.200',1234)) as client:
        assert login(client,password='wrong').status_code==429
    assert db.scalar(select(func.count()).select_from(LoginAttempt))==count_before


def test_logout_revokes_unused_brokerage_state(auth,monkeypatch):
    from urllib.parse import parse_qs,urlsplit
    from app.models import ZerodhaLoginState
    import httpx
    client,db=auth
    client.base_url=httpx.URL('http://127.0.0.1')
    for key,value in dict(ZERODHA_API_KEY='testapikey',ZERODHA_API_SECRET=SecretStr('testsecret'),ZERODHA_REDIRECT_URL='http://127.0.0.1/integrations/zerodha/callback',TOKEN_ENCRYPTION_KEY=SecretStr(Fernet.generate_key().decode())).items():monkeypatch.setattr(settings,key,value)
    csrf=login(client).json()['csrf_token']
    result=client.get('/integrations/zerodha/login',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
    raw=parse_qs(parse_qs(urlsplit(result.json()['login_url']).query)['redirect_params'][0])['state'][0]
    assert db.scalar(select(ZerodhaLoginState)) is not None
    assert client.post('/auth/logout',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}).status_code==200
    assert db.scalar(select(ZerodhaLoginState)) is None
    connected=MagicMock();monkeypatch.setattr(zerodha,'connect',connected)
    response=client.get('/integrations/zerodha/callback?request_token=testrequest&state='+raw,follow_redirects=False)
    assert response.status_code==303 and response.headers['location'].endswith('?zerodha=connect_failed')
    connected.assert_not_called()
