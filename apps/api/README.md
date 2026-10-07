# Family Investments API

Run commands from `apps/api` with `source ../../.venv/bin/activate`.
Install development dependencies with `python -m pip install -r requirements-dev.txt`.
Start the API with `uvicorn app.main:app --reload --port 8000`.

`DATABASE_URL` is optional for imports and `/health`. Configure a PostgreSQL URL
using the `postgresql+psycopg` driver when database access is needed. Engine
construction does not open a connection. `get_db` closes sessions; callers own
commit/rollback decisions. Never commit `.env` or credential values.

The schema is intended for one brokerage account. Family dashboard viewers are
not brokerage accounts. Credentials store only an encrypted access token. Brokerage access is read-only.

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
explicit sync validates the complete successful provider response, atomically
upserts returned account/exchange/symbol identities as active, marks absent
identities inactive, and updates the account sync timestamp. Missing identities
remain stored and can be reactivated by a later sync, including after a complete
empty response. Failed, malformed, duplicate or unauthenticated responses do not
change membership; persistence failures roll back every write. Sync and snapshot
creation share a per-account row lock. Current views use only active holdings;
historical snapshots are retained. There is no scheduler yet. Values use the requested `quantity` formula; `t1_quantity`
is stored separately and is not added to valuations. Decimal response values
serialize as strings; stored money rounds to four decimal places and percentages
to six. A zero-cost holding has zero percentage P&L.

Authoritative definitions live in `integrations/zerodha/buckets.py` (`REGISTRY`).
`classify_instrument(symbol, exchange, instrument_token)` is shared by holdings
and execution persistence and current execution/contribution reporting. NIFTYBEES
maps to NIFTY_50, MIDCAPETF to MID_CAP, HDFCSML250 to SMALL_CAP. Explicitly reviewed
legacy individual stocks are OTHER. Unknown identities become UNCLASSIFIED;
financial value is retained and reported separately, never silently folded into OTHER.

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

Classification is explicit in the version-controlled instrument registry. Each
reviewed definition has symbol, exchange aliases, optional known tokens, display
name, bucket and source. Duplicate aliases/tokens fail at import/startup. No name
heuristics infer market cap. Tokens may be reused by providers, so known-token
matches also require matching reviewed symbol/exchange metadata. Add a reviewed
instrument in one central location; no frontend classification rules exist. Existing stored classifications are read as stored and are
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
a missing target returns HTTP 404. Recorded delivery BUY executions are available separately; their historical coverage is explicitly incomplete.

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
last explicit holdings sync. Missing provider holdings remain stored as inactive
identities and are excluded from current holdings, summaries, allocation and new
snapshots. Run `alembic upgrade head` before starting the updated application;
migration `0002_holding_lifecycle` preserves existing holdings as active until
the next successful complete sync reconciles their membership.

The only POST routes update our own database (holdings sync, snapshot and canonical refresh). There
are no order creation, modification, cancellation, or selling operations.


## Canonical dashboard refresh and recorded executions

`POST /portfolio/refresh` validates the connected account/token, then fetches and validates complete holdings, current-day orders, actual trades and margins before writing. It holds the same account lock as holdings sync/snapshot creation and commits reconciliation, order/fill upserts, today's snapshot and `last_refresh_at` together. Failures roll back everything. `?if_stale=true` skips provider calls when the last full refresh is within five minutes on the current India date. Expiry returns normalized `reconnect_required`; other provider errors are sanitized.

`GET /portfolio/activity/today` separates actual executions from order context. Multiple fills aggregate by order/instrument/side/product using weighted prices. Identity includes account, execution date, exchange, provider order ID and trade ID; conflicting immutable fill replays are rejected. Order `book_date` records the current book independently from an older AMO placement timestamp. All financial persistence uses Decimal/Numeric. Charges and net amounts remain null when unavailable.

CNC BUY executions missing sufficient matching active holdings are `AWAITING_HOLDINGS`. Sufficient existing quantity is `HOLDING_PRESENT_UNCONFIRMED`: it cannot prove attribution to today's purchase. Daily purchases offset by sells are `NETTED_BY_SELLS`. SELL/non-delivery activity is `NOT_APPLICABLE`. These events never increase holdings valuation or snapshots. Holdings valuation retains the existing quantity-only formula; t1 quantity is used only as an attribution clue.

`GET /portfolio/contributions/month` sums only recorded CNC BUY fills in the current month. Orders, unfilled quantities, sells, intraday trades and unidentifiable legacy records do not count. `history_complete=false` and earliest recorded date disclose missing earlier history. No backfilled history, fabricated charges or monthly remaining/progress is supplied.

`refresh_portfolio(db, if_stale=False)` is reusable by a future external scheduled job with a managed DB session. No scheduler or cron endpoint is added, and nothing is deployed. Day-only trade books require daily collection to build history. Keep local services bound to loopback until dashboard authentication and deployment access controls exist.

Connection status adds local `token_valid`, backend `refresh_required` and `last_refresh_at`; early provider invalidation is detected on a read. Login's `return_to_dashboard=true` carries the return intent in encrypted callback state. Destination comes solely from backend `DASHBOARD_URL` (HTTPS in production, HTTP loopback allowed locally), with no credentials/query/fragment. The local default is `http://127.0.0.1:5173/`. Existing state cookie, TTL and exact callback validation remain enforced. Successful reconnect invalidates refresh freshness.

Apply `0003_execution_activity` after `0002_holding_lifecycle`. It extends existing orders/transactions/account tables and preserves existing records. Downgrade refuses unknown null charges/net amounts through PostgreSQL's NOT NULL constraint instead of inventing values; plan a deliberate data migration before downgrading.

Official order/trade semantics: [Kite orders documentation](https://kite.trade/docs/connect/v3/orders/).


## Classification migration and corrections

Apply `0004_classification` (file `0004_authoritative_classification.py`). It widens
bucket columns/check constraints, changes new-row defaults to UNCLASSIFIED and
adds nullable `portfolio_snapshots.unclassified_value`. Historical rows are not
rewritten: null means that allocation was not separately recorded. New snapshots
store unclassified value separately from Other, while totals still include it.
Holdings allocation uses classifications materialized by the authoritative sync.
Actual activity and monthly contribution reads resolve recorded instrument
identity through the same registry, so registry corrections apply to current
reporting. Canonical refresh corrects only the derived bucket on repeated fills;
immutable execution facts/identity and prior snapshots remain unchanged.
Downgrade refuses loss of nonzero unclassified snapshot allocation or any
UNCLASSIFIED bucket rather than silently changing it into Other.

## Railway deployment preparation

Deployment is not performed by these changes. Configure one backend service with
Root Directory `/apps/api` and explicitly select Config File Path
`/apps/api/railway.toml` (the config path is relative to the repository, not the
service root). Railpack detects `requirements.txt`; the equivalent install
command in that working directory is `python -m pip install -r requirements.txt`.
Use Python 3.12, the locally validated backend version.

The config starts a single process with:

```sh
sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers'
```

Railway supplies `PORT`. There is no reload mode or hard-coded port. The
pre-deploy command is `alembic upgrade head`, run once per deployment before the
new app starts; a failure blocks the deployment. No request or application
startup executes migrations. Review migration SQL and take a database backup
before release; use one migration runner and avoid concurrent releases. Existing
revisions 0001–0004 are unchanged. Current revision ID is `0004_classification`
(file `0004_authoritative_classification.py`). Do not run downgrades automatically.

Set these variables in Railway's backend service, never in frontend `VITE_`
variables or source control:

- `APP_ENV=production`, `DEBUG=false` (debug responses are forced off outside development).
- `DATABASE_URL`: reference the attached PostgreSQL service URL. `postgres://`,
  `postgresql://` and `postgresql+psycopg://` use the installed psycopg driver.
  URL credentials, query parameters and existing TLS options are preserved.
  Use the provider's required TLS/certificate policy for the selected connection;
  do not disable verification to work around failures.
- `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `TOKEN_ENCRYPTION_KEY`: existing backend
  configuration. Preserve the encryption key if migrating encrypted token data.
- `ZERODHA_REDIRECT_URL=https://<public-api-host>/integrations/zerodha/callback`:
  register exactly this HTTPS URL in the Kite developer console.
- `FRONTEND_ORIGIN=https://<frontend-host>`: exact origin, no trailing slash,
  path, query, credentials or wildcard. Required outside development; missing or
  invalid origins fail startup. Production allows only this origin. Development
  additionally allows `http://localhost:5173` and `http://127.0.0.1:5173`.
- `DASHBOARD_URL=https://<frontend-host>/`: required for the frontend's existing
  post-login dashboard return; it is server controlled.
- `FORWARDED_ALLOW_IPS`: Uvicorn's verified trusted ingress proxy IPs/CIDRs.
  Confirm the deployment's proxy source addresses and header handling before
  configuring trust. Do not blindly set `*`. Without correct trust the HTTPS
  callback can fail its existing exact scheme/host validation. Preserve the
  public Host header; do not add application proxy middleware or bypass callback
  validation. Uvicorn reads this variable directly; its default trusts loopback only.
- `APP_NAME` is optional; `PORT` is platform provided.

Railway health check path is `/health` (existing HTTP 200 process contract).
`/health/db` remains available for operational readiness: 200 reachable or
unconfigured, 503 configured but unreachable, with sanitized details. A process
health check alone does not prove that database credentials are configured;
verify `/health/db` after configuration.

Manual steps before public access: provision/reference PostgreSQL, verify backup
and migration results, configure secrets/domains/proxy trust, and register the
Kite callback. Zerodha authentication still requires a manual browser login when
the access token expires; no password/PIN/TOTP automation is provided. Use API and
frontend custom domains on the same site to preserve the existing SameSite=Lax
login-state cookie; unrelated domains can block the frontend's credentialed login
request. Check the callback in a real browser after eventual deployment.

The backend currently has no dashboard authentication. CORS is a browser origin
policy, not API access control: add an authenticated access boundary before making
financial endpoints publicly accessible. Keep production access gated until then.
Railway/proxy log retention must also exclude callback query strings; application
Uvicorn access logging already strips them. No settings/credentials are logged;
SQLAlchemy hides bound parameters and production debug tracebacks are disabled.
Investment endpoints remain brokerage read-only.

References: [Railway config](https://docs.railway.com/config-as-code/reference),
[monorepo roots](https://docs.railway.com/deployments/monorepo),
[pre-deploy migrations](https://docs.railway.com/deployments/pre-deploy-command),
[Uvicorn proxy trust](https://www.uvicorn.org/settings/).
