"""Deployment contracts: no live database, network or credential values."""
from pathlib import Path
import tomllib
import pytest
from app.config import Settings


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_database_driver_normalization_preserves_tls(scheme):
    settings = Settings(_env_file=None, DATABASE_URL=f'{scheme}://user:fake%40password@host:5432/db?sslmode=verify-full&sslrootcert=%2Fcert.pem')
    url = settings.database_url()
    assert url.drivername == 'postgresql+psycopg'
    assert url.password == 'fake@password'
    assert url.query == {'sslmode':'verify-full', 'sslrootcert':'/cert.pem'}
    assert 'fake@password' not in str(url)


def test_invalid_database_url_error_is_sanitized():
    with pytest.raises(RuntimeError) as error:
        Settings(_env_file=None, DATABASE_URL='private-invalid-secret').database_url()
    assert 'private-invalid-secret' not in str(error.value)


def test_railway_commands_and_health_contract():
    config = tomllib.loads((Path(__file__).resolve().parents[1] / 'railway.toml').read_text())['deploy']
    assert '--host 0.0.0.0' in config['startCommand']
    assert '--port "$PORT"' in config['startCommand']
    assert '--reload' not in config['startCommand']
    assert config['preDeployCommand'] == ['alembic upgrade head']
    assert config['healthcheckPath'] == '/health'


def test_trusted_proxy_restores_https_without_trusting_arbitrary_clients():
    import asyncio
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    async def run(client):
        seen = {}
        async def downstream(scope, receive, send):
            seen.update(scope)
        middleware = ProxyHeadersMiddleware(downstream, trusted_hosts=['10.0.0.1'])
        await middleware({'type':'http', 'scheme':'http', 'client':(client,123), 'headers':[(b'x-forwarded-proto',b'https')]}, None, None)
        return seen['scheme']
    assert asyncio.run(run('10.0.0.1')) == 'https'
    assert asyncio.run(run('10.0.0.2')) == 'http'


def test_production_debug_disabled_even_if_debug_variable_is_true():
    import os
    import subprocess
    import sys
    environment = {**os.environ, 'APP_ENV':'production', 'DEBUG':'true',
                   'FRONTEND_ORIGIN':'https://dashboard.example.com',
                   'DATABASE_URL':'postgresql://user:fakepassword@localhost/db'}
    result = subprocess.run([sys.executable, '-c',
        'from app.main import app; assert app.debug is False; print("production debug disabled")'],
        env=environment, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'production debug disabled'
    assert 'fakepassword' not in result.stdout + result.stderr
