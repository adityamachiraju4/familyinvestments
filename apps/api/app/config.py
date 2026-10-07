"""Environment-based application settings with safe development defaults."""

from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Non-secret settings; environment variables override the optional .env."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DASHBOARD_USERNAME: str | None = None
    DASHBOARD_PASSWORD_HASH: SecretStr | None = None
    SESSION_SECRET: SecretStr | None = None
    SESSION_TTL_SECONDS: int = 28800
    APP_NAME: str = "Family Investments API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    FRONTEND_ORIGIN: str | None = None
    DASHBOARD_URL: str | None = None
    DATABASE_URL: str | None = None
    ZERODHA_API_KEY: str | None = None
    ZERODHA_API_SECRET: SecretStr | None = None
    ZERODHA_REDIRECT_URL: str | None = None
    TOKEN_ENCRYPTION_KEY: SecretStr | None = None


    def cors_origins(self) -> list[str]:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"] if self.APP_ENV == "development" else []
        if not self.FRONTEND_ORIGIN:
            if self.APP_ENV != "development":
                raise RuntimeError("FRONTEND_ORIGIN must be configured outside development")
            return origins
        try:
            url = urlsplit(self.FRONTEND_ORIGIN)
            url.port
            if (not url.hostname or url.username or url.password or url.query or url.fragment
                    or url.path or url.scheme not in {"http", "https"}
                    or (self.APP_ENV != "development" and (url.scheme != "https" or url.hostname in {"localhost", "127.0.0.1", "::1"}))):
                raise ValueError
        except ValueError:
            raise RuntimeError("FRONTEND_ORIGIN must be an explicit valid origin (HTTPS outside development)") from None
        return list(dict.fromkeys([*origins, self.FRONTEND_ORIGIN]))

    def database_url(self):
        """Select installed psycopg driver while preserving credentials and TLS options."""
        if not self.DATABASE_URL:
            return None
        try:
            url = make_url(self.DATABASE_URL)
            if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
                raise ValueError
            return url.set(drivername="postgresql+psycopg")
        except (ArgumentError, ValueError):
            raise RuntimeError("DATABASE_URL must be a valid PostgreSQL URL") from None


settings = Settings()
