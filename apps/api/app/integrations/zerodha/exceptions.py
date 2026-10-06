"""Fixed, safe errors; never attach provider messages or secret values."""


class IntegrationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def configuration_error() -> IntegrationError:
    return IntegrationError("configuration_missing", "Zerodha integration is not configured")


def credentials_error() -> IntegrationError:
    return IntegrationError("credentials_invalid", "Reconnect Zerodha to obtain a valid session", 401)


def provider_error() -> IntegrationError:
    return IntegrationError("provider_error", "Zerodha request failed", 502)
