from fastapi.testclient import TestClient
from app.main import app


def test_development_origin_preflight():
    response = TestClient(app).options('/portfolio/snapshots/today', headers={
        'Origin': 'http://127.0.0.1:5173',
        'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'
    assert response.headers['access-control-allow-credentials'] == 'true'
    assert 'X-CSRF-Token' in response.headers['access-control-allow-headers']


def test_unknown_origin_is_rejected():
    response = TestClient(app).options('/portfolio/snapshots/today', headers={
        'Origin': 'https://untrusted.example',
        'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers


def configured_client(environment, origin=None):
    from fastapi import FastAPI
    from app.config import Settings
    from app.main import configure_cors
    application = FastAPI()
    configure_cors(application, Settings(_env_file=None, APP_ENV=environment, FRONTEND_ORIGIN=origin))
    return TestClient(application)


def preflight(client, origin):
    return client.options('/portfolio/refresh', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'POST',
    })


def test_production_only_allows_explicit_frontend():
    client = configured_client('production', 'https://dashboard.example.com')
    response = preflight(client, 'https://dashboard.example.com')
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://dashboard.example.com'
    assert response.headers['access-control-allow-credentials'] == 'true'
    assert 'X-CSRF-Token' in response.headers['access-control-allow-headers']
    for origin in ('http://localhost:5173', 'http://127.0.0.1:5173', 'https://attacker.example'):
        response = preflight(client, origin)
        assert response.status_code == 400
        assert 'access-control-allow-origin' not in response.headers


def test_development_keeps_both_loopback_origins():
    client = configured_client('development')
    for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
        assert preflight(client, origin).status_code == 200


def test_missing_production_frontend_fails_closed():
    import pytest
    with pytest.raises(RuntimeError, match='FRONTEND_ORIGIN must be configured'):
        configured_client('production')


def test_invalid_production_origins_fail_closed():
    import pytest
    for origin in ('*', 'https://example.com/', 'https://example.com/path', 'http://example.com', 'https://localhost', 'https://user:password@example.com', 'https://example.com?x=1'):
        with pytest.raises(RuntimeError):
            configured_client('production', origin)
