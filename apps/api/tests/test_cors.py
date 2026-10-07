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


def test_unknown_origin_is_rejected():
    response = TestClient(app).options('/portfolio/snapshots/today', headers={
        'Origin': 'https://untrusted.example',
        'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers
