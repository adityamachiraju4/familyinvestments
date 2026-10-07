"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import database
from app.config import settings
from app.portfolio.routes import router as portfolio_router
from app.integrations.zerodha.exceptions import IntegrationError
from app.integrations.zerodha.routes import router as zerodha_router

app = FastAPI(title=settings.APP_NAME, version="0.1.0", debug=settings.DEBUG)

if settings.APP_ENV == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )


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


@app.exception_handler(IntegrationError)
async def integration_error_handler(request, exc: IntegrationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


app.include_router(zerodha_router)

app.include_router(portfolio_router)
