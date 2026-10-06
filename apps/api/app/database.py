"""SQLAlchemy metadata and optional database sessions."""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base with deterministic constraint names."""

    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


engine = (
    create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    if settings.DATABASE_URL else None
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False) if engine is not None else None


def get_db() -> Generator[Session, None, None]:
    """Yield a session; callers explicitly commit their own transactions."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL must be configured to use database sessions")
    with SessionLocal() as session:
        yield session
