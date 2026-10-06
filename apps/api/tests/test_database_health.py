"""Database readiness checks use mocked connections, never a live server."""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app import database
from app.main import app


def request(path: str) -> httpx.Response:
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)
    return asyncio.run(run())


def test_database_unconfigured(monkeypatch):
    monkeypatch.setattr(database, "engine", None)
    response = request("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "unconfigured", "database": "not_configured"}


def test_database_reachable_and_connection_closed(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(database, "engine", engine)
    response = request("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
    connection = engine.connect.return_value.__enter__.return_value
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    engine.connect.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("failure", ["connect", "query"])
def test_database_unreachable_does_not_leak_details(monkeypatch, failure):
    engine = MagicMock()
    error = OperationalError(None, None, Exception("postgresql://private_user:secret_password@private_host/db"))
    if failure == "connect":
        engine.connect.side_effect = error
    else:
        engine.connect.return_value.__enter__.return_value.execute.side_effect = error
    monkeypatch.setattr(database, "engine", engine)
    response = request("/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unreachable"}
    for detail in ("private_user", "secret_password", "private_host", "postgresql"):
        assert detail not in response.text
    if failure == "query":
        engine.connect.return_value.__exit__.assert_called_once()
    assert request("/health").json() == {"status": "ok", "service": "family-investments-api"}
