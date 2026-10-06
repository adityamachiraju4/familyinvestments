# Family Investments API

Run commands from `apps/api` with `source ../../.venv/bin/activate`.
Install development dependencies with `python -m pip install -r requirements-dev.txt`.
Start the API with `uvicorn app.main:app --reload --port 8000`.

`DATABASE_URL` is optional for imports and `/health`. Configure a PostgreSQL URL
using the `postgresql+psycopg` driver when database access is needed. Engine
construction does not open a connection. `get_db` closes sessions; callers own
commit/rollback decisions. Never commit `.env` or credential values.

The schema is intended for one brokerage account. Family dashboard viewers are
not brokerage accounts. Credentials store only an encrypted token; encryption
and brokerage API calls are not implemented.

Money uses `Numeric(20, 4)` and percentages use `Numeric(12, 6)`. Quantities are
integers. Timestamps carry timezone information. `updated_at` changes on
SQLAlchemy-issued updates; direct SQL writers must update it themselves.
Current holdings are unique per account/exchange/symbol. Monthly target dates
normalize to the first of the month in the ORM and have a database check.
Bucket values are enforced by database check constraints.

Alembic reads the application settings and model metadata. After a PostgreSQL
database has been provisioned separately, apply the schema with `alembic upgrade head`.
This repository does not create the database. To inspect SQL without connecting,
set a placeholder PostgreSQL `DATABASE_URL` and use `alembic upgrade head --sql`.
`alembic downgrade head:base --sql` inspects the reverse migration without execution.

Validate without a live database with `python -m pytest -q` and
`python -m compileall -q app alembic tests`.

Database readiness is available at `/health/db`: HTTP 200 when reachable or
unconfigured, and HTTP 503 when configured but unreachable. Responses omit
connection details. PostgreSQL connection attempts have a five-second timeout.
`/health` remains the process health endpoint and does not query the database.

To insert safe local account metadata after migrating, run
`python -m scripts.seed_dev` from `apps/api`. This explicit, idempotent utility
inserts `LOCAL_DEV` once and preserves existing account metadata. It never
inserts credentials or runs on startup. Local connection settings belong only
in the gitignored `.env`.

## Read-only Zerodha integration

Set these values in `apps/api/.env` or the process environment:

- `ZERODHA_API_KEY`: your Kite Connect application key.
- `ZERODHA_API_SECRET`: your application secret, used only by the backend.
- `ZERODHA_REDIRECT_URL`: `http://127.0.0.1:8000/integrations/zerodha/callback`
  for local development. Register the exact same URL in the Kite developer console.
- `TOKEN_ENCRYPTION_KEY`: a Fernet key, generated once and saved securely.

Generate a key locally using
`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
Keep this key stable: replacing it makes existing stored tokens unreadable and
requires reauthentication. There is no default key. No secrets belong in source,
command history, screenshots, or tracked files.

From `apps/api`, activate the virtual environment and run:

```bash
source ../../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/integrations/zerodha/login` in your browser. Follow
its returned `login_url` in that same browser within ten minutes. The login
response sets an HttpOnly state cookie; the callback verifies it and the
registered callback location. Kite itself redirects to the registered URL;
`redirect_params` carries the state and does not override that URL. Do not
manually paste callback tokens into terminal commands or logs.

The callback exchanges the one-time request token using the documented SHA-256
checksum, then stores only a Fernet-encrypted access token. On first login,
`LOCAL_DEV` becomes the authenticated Kite `user_id`; future logins must match
that account. Do not rerun the development seed after binding a real account.
Zero or multiple account rows cause a safe configuration failure. No password,
PIN, TOTP, API secret, or request token is persisted. Tokens expire at 06:00 IST
on the next day; early provider invalidation also requires login again. A
`connected` status records the last successful login, not a real-time token check.

Read or synchronize with:

```bash
curl http://127.0.0.1:8000/integrations/zerodha/status
curl http://127.0.0.1:8000/portfolio/funds
curl -X POST http://127.0.0.1:8000/integrations/zerodha/sync/holdings
curl http://127.0.0.1:8000/portfolio/holdings
```

Funds are fetched live from equity margins. Holdings are read from PostgreSQL;
explicit sync fetches holdings and atomically upserts returned rows and the
account sync timestamp. Missing symbols are retained, including after an empty
provider response; these rows may be stale. There is no deletion/reconciliation
or scheduler yet. Values use the requested `quantity` formula; `t1_quantity`
is stored separately and is not added to valuations. Decimal response values
serialize as strings; stored money rounds to four decimal places and percentages
to six. A zero-cost holding has zero percentage P&L.

Bucket mappings live in `integrations/zerodha/buckets.py` (`SYMBOL_BUCKETS`): `NIFTYBEES` maps to `NIFTY_50`,
`MIDCAPETF` to `MID_CAP`, and unknown symbols to `OTHER`.

This integration has no order placement, modification, cancellation, selling,
positions, or derivatives operations. Local sync writes only our database.
Endpoints still have no application authentication; keep the API bound to
loopback. Errors use fixed messages and omit provider bodies and connection
values. The callback query is redacted from Uvicorn access logs; any future
proxy must also exclude callback query strings from logging. No automatic
provider retries are made. Ordinary tests use mocked HTTP and isolated SQLite
storage and do not contact Kite or PostgreSQL.

Official references:
[authentication and equity margins](https://kite.trade/docs/connect/v3/user/)
and [holdings](https://kite.trade/docs/connect/v3/portfolio/).

## Funds, summary, daily snapshots, and monthly targets

Dashboard `available_cash` means the latest usable equity balance. The provider
fields are normalized in this order: `available.live_balance` when non-null,
otherwise `net`, otherwise raw `available.cash` as a last resort. Zero and negative
values are valid; neither is treated as absent. Opening balance never substitutes
for current cash. `opening_balance`, `live_balance`, and `net` retain their own
provider meanings. Missing usable balances, non-finite numbers, or malformed
fields return a sanitized provider error, not a fabricated zero. Thus opening
cash of -1123.50 with live balance/net of 5099.50 yields available cash 5099.50.

`GET /portfolio/summary` combines stored holdings with live funds:

- Invested value is the sum of stored `invested_value`.
- Market value is the sum of stored `current_value`.
- Total account value is market value plus current available cash.
- Total P&L is market value minus invested value; cash is excluded.
- P&L percent is P&L divided by invested value times 100, or zero when invested
  value is not positive. Percentage output rounds to six decimal places.
- Allocation gives market values for all five buckets and sums to market value.

Classification is explicit in `SYMBOL_BUCKETS`. Individual equities stay `OTHER`.
Add the chosen small-cap ETF with `Bucket.SMALL_CAP` in that mapping when decided;
no symbol is guessed. Existing stored classifications are read as stored and are
not retroactively rewritten by summary/snapshot requests. Prices are never
adjusted based on assumptions about corporate actions or unusually large P&L.

`POST /portfolio/snapshots/today` requires a connected account with a valid stored
token. It fetches live funds and uses the current DB holdings, without refreshing
prices or syncing holdings implicitly. Dates use Asia/Kolkata. One transaction
upserts the account/date portfolio row and each account/date/exchange/symbol
holding row. Repeated calls update those rows, preserve their `created_at`, and
replace that date's holding membership to match current DB holdings. Other dates
are untouched. Any database failure rolls back the entire operation. There is
no automatic scheduler.

Snapshot `portfolio_value` means holdings market value; `total_account_value`
adds cash. `day_pnl` is stored as zero to mean **unavailable**, not a measured zero
return: this integration does not have sufficient reliable daily-return inputs.
The existing snapshot schema has no separate large-cap column, so snapshot
`other_value` includes `LARGE_CAP` plus `OTHER`; summary allocation and individual
holding history keep those buckets separate. No schema migration is needed.

`GET /portfolio/snapshots?limit=30` returns the newest N snapshots in chronological
ascending order. `GET /portfolio/holdings/{tradingsymbol}/history?limit=30` returns
the newest N symbol rows ascending by date, then exchange. The symbol endpoint
includes all exchanges with separate rows. Both limits range from 1 to 3650;
an empty history returns an empty list. Snapshots are our recorded history and
cannot reconstruct dates before snapshot collection started.

`GET /portfolio/monthly-target` defaults to the current month in Asia/Kolkata.
Use `?month=2026-10` for a specific month. Dates normalize to the month's first day;
a missing target returns HTTP 404. No investment-progress claim is made because
reliable persisted trade history is not populated yet.

Seed/update the agreed October 2026 target explicitly with:

```bash
python -m scripts.seed_monthly_target
```

The idempotent utility selects the existing single account and writes only
`monthly_targets`: total 15000, Nifty 8000, midcap 5000, smallcap 2000. These figures
are seed data, not global calculation constants; it never reseeds the account or
changes credentials. Rerunning intentionally restores these agreed target values.

The [Personal API plan](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/what-are-the-charges-for-kite-apis)
does not include historical or real-time market data feeds. This implementation
uses account funds/holdings only, and does not fetch candles, fabricate market
history, or infer daily returns from lifetime P&L. Price freshness is tied to the
last explicit holdings sync. Missing provider holdings remain in current storage
under the existing upsert-only sync policy and can consequently appear in summaries
and snapshots until deliberate reconciliation is implemented.

The only POST routes update our own database (holdings sync and snapshot). There
are no order creation, modification, cancellation, or selling operations.
