"""Validate schema contracts and PostgreSQL migration DDL without a live DB."""

from datetime import date
from io import StringIO
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
import asyncio
import httpx
import pytest
from sqlalchemy import CheckConstraint, Date, Index, MetaData, Numeric, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn, CreateTable

from app.database import Base
from app.main import app
from app.models import Bucket, MonthlyTarget

API_ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "zerodha_accounts", "zerodha_credentials", "holdings", "portfolio_snapshots",
    "holding_snapshots", "orders", "monthly_targets", "investment_transactions",
    "dashboard_sessions", "dashboard_login_attempts", "zerodha_login_states",
}
UNIQUES = {
    "zerodha_accounts": ("client_id",),
    "zerodha_credentials": ("account_id",),
    "holdings": ("account_id", "exchange", "tradingsymbol"),
    "portfolio_snapshots": ("account_id", "snapshot_date"),
    "holding_snapshots": ("account_id", "snapshot_date", "exchange", "tradingsymbol"),
    "orders": ("account_id", "zerodha_order_id"),
    "monthly_targets": ("account_id", "month"),
}
MONEY_FIELDS = {
    "holdings": "average_price last_price invested_value current_value unrealised_pnl unrealised_pnl_percent",
    "portfolio_snapshots": "available_cash holdings_invested_value holdings_market_value portfolio_value total_account_value day_pnl total_pnl total_pnl_percent nifty_value midcap_value smallcap_value other_value unclassified_value",
    "holding_snapshots": "average_price last_price invested_value market_value pnl pnl_percent",
    "orders": "price average_price",
    "monthly_targets": "total_target nifty_target midcap_target smallcap_target",
    "investment_transactions": "price gross_amount charges net_amount",
}


def test_expected_tables():
    assert set(Base.metadata.tables) == TABLES | {"mutual_fund_accounts", "mutual_fund_schemes", "sips", "mutual_fund_transactions", "mutual_fund_holdings"}
    assert all(list(table.primary_key.columns.keys()) == ["id"] for name, table in Base.metadata.tables.items() if name != "mutual_fund_holdings")


@pytest.mark.parametrize("table,columns", UNIQUES.items())
def test_unique_constraints(table, columns):
    assert columns in {
        tuple(c.columns.keys()) for c in Base.metadata.tables[table].constraints
        if isinstance(c, UniqueConstraint)
    }


@pytest.mark.parametrize("name", sorted(TABLES - {"zerodha_accounts", "dashboard_sessions", "dashboard_login_attempts"}))
def test_account_foreign_keys(name):
    column = Base.metadata.tables[name].c.account_id
    assert not column.nullable
    assert {fk.target_fullname for fk in column.foreign_keys} == {"zerodha_accounts.id"}


def test_optional_order_reference():
    column = Base.metadata.tables["investment_transactions"].c.order_id
    assert column.nullable
    assert {fk.target_fullname for fk in column.foreign_keys} == {"orders.id"}


@pytest.mark.parametrize("table,fields", MONEY_FIELDS.items())
def test_decimal_money_columns(table, fields):
    for field in fields.split():
        column = Base.metadata.tables[table].c[field]
        assert isinstance(column.type, Numeric)
        assert column.type.asdecimal
        assert column.type.precision is not None
        assert column.type.scale is not None


@pytest.mark.parametrize("name", ["holdings", "holding_snapshots", "investment_transactions"])
def test_buckets_are_constrained(name):
    table = Base.metadata.tables[name]
    enum = table.c.bucket.type
    assert set(enum.enums) == {bucket.value for bucket in Bucket}
    assert enum.validate_strings
    with pytest.raises(LookupError):
        enum.bind_processor(postgresql.dialect())("INVALID")
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert len(checks) == 1
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for bucket in Bucket:
        assert f"'{bucket.value}'" in ddl


def test_month_is_normalized_and_database_constrained():
    assert MonthlyTarget(month=date(2026, 10, 23)).month == date(2026, 10, 1)
    table = Base.metadata.tables["monthly_targets"]
    assert isinstance(table.c.month.type, Date)
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "EXTRACT(DAY FROM month) = 1" in ddl


def test_snapshot_index_and_credential_safety():
    indexes = Base.metadata.tables["holding_snapshots"].indexes
    assert ("account_id", "snapshot_date") in {tuple(i.columns.keys()) for i in indexes}
    token = Base.metadata.tables["zerodha_credentials"].c.encrypted_access_token
    assert token.default is None and token.server_default is None
    assert not token.nullable
    status = Base.metadata.tables["zerodha_accounts"].c.connection_status
    assert status.server_default.arg == "disconnected"


@pytest.mark.parametrize("url", [None, ""])
def test_imports_and_health_without_database_url(url):
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    if url is not None:
        env["DATABASE_URL"] = url
    code = (
        "import app.config; app.config.settings = app.config.Settings(_env_file=None); "
        "import app.main, app.config, app.database, app.models; "
        "assert app.database.engine is None; "
        "assert app.database.SessionLocal is None; "
        "assert app.main.health() == {'status': 'ok', 'service': 'family-investments-api'}; "
        "db = app.database.get_db(); "
        "\ntry: next(db)\nexcept RuntimeError as exc: assert 'DATABASE_URL' in str(exc)"
        "\nelse: raise AssertionError('Unconfigured session must fail explicitly')"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=API_ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    async def check_http():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "family-investments-api"}
            assert (await client.get("/docs")).status_code == 200
    asyncio.run(check_http())


def test_configured_engine_is_lazy_and_session_closes():
    code = (
        "import app.database as db; from unittest.mock import MagicMock; "
        "assert db.engine is not None; assert db.SessionLocal is not None; "
        "assert db.engine.pool.checkedout() == 0; "
        "session = MagicMock(); factory = MagicMock(); "
        "factory.return_value.__enter__.return_value = session; db.SessionLocal = factory; "
        "dependency = db.get_db(); assert next(dependency) is session; dependency.close(); "
        "factory.return_value.__exit__.assert_called_once(); db.engine.dispose()"
    )
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg://USER:PASSWORD@127.0.0.1:1/DBNAME"}
    result = subprocess.run([sys.executable, "-c", code], cwd=API_ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def load_revision():
    spec = importlib.util.spec_from_file_location("initial_schema", API_ROOT / "alembic/versions/0001_initial_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_migration_matches_model_metadata(monkeypatch):
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    context = MigrationContext.configure(dialect_name="postgresql", opts={"target_metadata": metadata})
    operations = Operations(context)

    def capture_table(name, *args, **kwargs):
        from sqlalchemy import Table
        return Table(name, metadata, *args, **kwargs)

    monkeypatch.setattr(operations, "create_table", capture_table)
    def capture_index(name, table, columns, **kwargs):
        Index(name, *(metadata.tables[table].c[column] for column in columns), **kwargs)

    monkeypatch.setattr(operations, "create_index", capture_index)
    revision = load_revision()
    monkeypatch.setattr(revision, "op", operations)
    revision.upgrade()
    # Frozen revisions together must match the current model, without editing 0001.
    lifecycle_spec = importlib.util.spec_from_file_location(
        "holding_lifecycle", API_ROOT / "alembic/versions/0002_holding_lifecycle.py",
    )
    lifecycle = importlib.util.module_from_spec(lifecycle_spec)
    lifecycle_spec.loader.exec_module(lifecycle)
    monkeypatch.setattr(operations, "add_column", lambda table, column: metadata.tables[table].append_column(column))
    monkeypatch.setattr(lifecycle, "op", operations)
    lifecycle.upgrade()
    spec = importlib.util.spec_from_file_location("execution_activity", API_ROOT / "alembic/versions/0003_execution_activity.py")
    executions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(executions)
    def alter_column(table, column, **kwargs):
        col = metadata.tables[table].c[column]
        if "nullable" in kwargs:
            col.nullable = kwargs["nullable"]
        if "type_" in kwargs:
            col.type = kwargs["type_"]
        if "server_default" in kwargs:
            from sqlalchemy import DefaultClause
            col.server_default = DefaultClause(kwargs["server_default"])
    def unique(name, table, columns):
        metadata.tables[table].append_constraint(UniqueConstraint(*columns, name=name))
    monkeypatch.setattr(operations, "alter_column", alter_column)
    monkeypatch.setattr(operations, "create_unique_constraint", unique)
    monkeypatch.setattr(executions, "op", operations)
    executions.upgrade()
    spec = importlib.util.spec_from_file_location("classification", API_ROOT / "alembic/versions/0004_authoritative_classification.py")
    classification = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(classification)
    def drop_constraint(name, table, **kwargs):
        target = metadata.tables[table]
        target.constraints.remove(next(c for c in target.constraints if c.name == name))
    def check(name, table, condition):
        from sqlalchemy import CheckConstraint
        metadata.tables[table].append_constraint(CheckConstraint(condition, name=name))
    monkeypatch.setattr(operations, "drop_constraint", drop_constraint)
    monkeypatch.setattr(operations, "create_check_constraint", check)
    monkeypatch.setattr(classification, "op", operations)
    classification.upgrade()
    spec = importlib.util.spec_from_file_location("dashboard_auth", API_ROOT / "alembic/versions/0005_dashboard_auth.py")
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    monkeypatch.setattr(auth, "op", operations)
    auth.upgrade()
    spec = importlib.util.spec_from_file_location("zerodha_login", API_ROOT / "alembic/versions/0006_zerodha_login_state.py")
    login_state = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(login_state)
    monkeypatch.setattr(login_state, "op", operations)
    login_state.upgrade()
    assert set(metadata.tables) == TABLES
    dialect = postgresql.dialect()
    for name in TABLES:
        actual = metadata.tables[name]
        expected = Base.metadata.tables[name]
        assert {c.name: str(CreateColumn(c).compile(dialect=dialect)) for c in actual.columns} == {
            c.name: str(CreateColumn(c).compile(dialect=dialect)) for c in expected.columns
        }
        # Constraint ordering is arbitrary; compare their PostgreSQL definitions.
        def constraints(table):
            ddl = str(CreateTable(table).compile(dialect=dialect))
            return sorted(line.strip().rstrip(",") for line in ddl.splitlines() if "CONSTRAINT " in line)
        assert constraints(actual) == constraints(expected)
        assert {(i.name, tuple(i.columns.keys()), i.unique) for i in actual.indexes} == {
            (i.name, tuple(i.columns.keys()), i.unique) for i in expected.indexes
        }


def test_alembic_offline_upgrade_and_downgrade(monkeypatch):
    import app.config
    monkeypatch.setattr(app.config.settings, "DATABASE_URL", "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME")
    output = StringIO()
    config = Config(str(API_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    for table in TABLES:
        assert f"CREATE TABLE {table}" in sql
    for table in ("holdings", "holding_snapshots", "investment_transactions"):
        assert sql.count(f"CONSTRAINT ck_{table}_bucket CHECK") == 2
    assert "CREATE INDEX ix_holding_snapshots_account_date" in sql
    assert "ALTER TABLE holdings ADD COLUMN is_active BOOLEAN DEFAULT true NOT NULL" in sql
    output.seek(0)
    output.truncate()
    command.downgrade(config, "head:base", sql=True)
    assert "ALTER TABLE holdings DROP COLUMN is_active" in output.getvalue()
    for table in TABLES:
        assert f"DROP TABLE {table}" in output.getvalue()
