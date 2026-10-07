"""Thin Kite v3 client limited to session exchange and read-only equity data."""

from decimal import Decimal
import hashlib
import json
import re
from urllib.parse import urlencode, urlsplit

import httpx

from app.config import settings
from app.integrations.zerodha.crypto import cipher
from app.integrations.zerodha.exceptions import configuration_error, credentials_error, provider_error


def require_config() -> None:
    values = (settings.ZERODHA_API_KEY, settings.ZERODHA_API_SECRET, settings.ZERODHA_REDIRECT_URL)
    if not all(values):
        raise configuration_error()
    if not re.fullmatch(r"[A-Za-z0-9]+", settings.ZERODHA_API_KEY):
        raise configuration_error()
    if not settings.ZERODHA_API_SECRET.get_secret_value():
        raise configuration_error()
    try:
        url = urlsplit(settings.ZERODHA_REDIRECT_URL)
        url.port  # Validate malformed ports without exposing the input.
    except ValueError:
        raise configuration_error() from None
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise configuration_error()
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise configuration_error()
    if url.path != "/integrations/zerodha/callback":
        raise configuration_error()
    cipher()  # Fail before starting auth if encryption is unavailable.


def login_url(state: str) -> str:
    require_config()
    return "https://kite.zerodha.com/connect/login?" + urlencode({
        "v": "3", "api_key": settings.ZERODHA_API_KEY,
        "redirect_params": urlencode({"state": state}),
    })


class KiteClient:
    def __init__(self, access_token: str | None = None):
        require_config()
        if access_token is not None and not re.fullmatch(r"[A-Za-z0-9]+", access_token):
            raise credentials_error()
        self._access_token = access_token

    def _request(self, method: str, path: str, data: dict | None = None):
        headers = {"X-Kite-Version": "3"}
        if self._access_token:
            headers["Authorization"] = f"token {settings.ZERODHA_API_KEY}:{self._access_token}"
        try:
            with httpx.Client(base_url="https://api.kite.trade", timeout=10, trust_env=False) as client:
                response = client.request(method, path, headers=headers, data=data)
            if response.status_code in {401, 403}:
                raise credentials_error()
            if not response.is_success:
                raise provider_error()
            payload = json.loads(response.content, parse_float=Decimal)
            if not isinstance(payload, dict):
                raise provider_error()
            if payload.get("error_type") == "TokenException":
                raise credentials_error()
            if payload.get("status") != "success" or "data" not in payload:
                raise provider_error()
            return payload["data"]
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise provider_error() from None

    def exchange_token(self, request_token: str):
        checksum = hashlib.sha256((settings.ZERODHA_API_KEY + request_token + settings.ZERODHA_API_SECRET.get_secret_value()).encode()).hexdigest()
        return self._request("POST", "/session/token", {
            "api_key": settings.ZERODHA_API_KEY, "request_token": request_token, "checksum": checksum,
        })

    def get_margins(self):
        if not self._access_token:
            raise credentials_error()
        return self._request("GET", "/user/margins/equity")

    def get_holdings(self):
        if not self._access_token:
            raise credentials_error()
        return self._request("GET", "/portfolio/holdings")

    def get_orders(self):
        if not self._access_token:
            raise credentials_error()
        return self._request("GET", "/orders")

    def get_trades(self):
        if not self._access_token:
            raise credentials_error()
        return self._request("GET", "/trades")

    def get_positions(self):
        if not self._access_token:
            raise credentials_error()
        return self._request("GET", "/portfolio/positions")
