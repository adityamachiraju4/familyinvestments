"""Authenticated token encryption using an explicitly configured Fernet key."""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.integrations.zerodha.exceptions import configuration_error, credentials_error


def cipher() -> Fernet:
    if not settings.TOKEN_ENCRYPTION_KEY:
        raise configuration_error()
    try:
        return Fernet(settings.TOKEN_ENCRYPTION_KEY.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeError):
        raise configuration_error() from None


def encrypt_token(token: str) -> str:
    return cipher().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(encrypted: str, ttl: int | None = None) -> str:
    try:
        return cipher().decrypt(encrypted.encode("ascii"), ttl=ttl).decode("utf-8")
    except (InvalidToken, UnicodeError):
        raise credentials_error() from None
