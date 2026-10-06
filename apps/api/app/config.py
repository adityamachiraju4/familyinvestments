"""Environment-based application settings with safe development defaults."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Non-secret settings; environment variables override the optional .env."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Family Investments API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    DATABASE_URL: str | None = None
    ZERODHA_API_KEY: str | None = None
    ZERODHA_API_SECRET: SecretStr | None = None
    ZERODHA_REDIRECT_URL: str | None = None
    TOKEN_ENCRYPTION_KEY: SecretStr | None = None


settings = Settings()
