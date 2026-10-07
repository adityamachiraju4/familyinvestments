"""FastAPI application entry point."""

from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from app.auth.service import require_access, validate_config
from app.auth.routes import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import database
from app.config import settings
from app.portfolio.routes import router as portfolio_router
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.routes import router as zerodha_router, callback_router

@asynccontextmanager
async def lifespan(application):
    validate_config()
    if database.SessionLocal is None:
        raise RuntimeError("Database must be configured for dashboard authentication")
    yield


app = FastAPI(lifespan=lifespan, title=settings.APP_NAME, version="0.1.0", debug=settings.DEBUG if settings.APP_ENV == "development" else False)

def configure_cors(application: FastAPI, configuration) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    )


configure_cors(app, settings)

@app.middleware("http")
async def private_cache_policy(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/auth/", "/portfolio/", "/integrations/zerodha/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the API is running."""
    return {"status": "ok", "service": "family-investments-api"}


@app.get("/health/db", response_model=None)
def database_health() -> dict[str, str] | JSONResponse:
    """Check database connectivity without exposing connection details."""
    if database.engine is None:
        return {"status": "unconfigured", "database": "not_configured"}
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unreachable"},
        )
    return {"status": "ok", "database": "reachable"}


@app.exception_handler(RequestValidationError)
async def safe_auth_validation(request, exc):
    if request.url.path == "/auth/login":
        return JSONResponse(status_code=400, content={"message": "Invalid login request"}, headers={"Cache-Control": "no-store"})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(IntegrationError)
async def integration_error_handler(request, exc: IntegrationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


app.include_router(auth_router)
app.include_router(zerodha_router, dependencies=[Depends(require_access)])
app.include_router(callback_router)

app.include_router(portfolio_router, dependencies=[Depends(require_access)])
