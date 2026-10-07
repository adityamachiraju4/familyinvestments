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

After signing into the household dashboard, use **Connect Zerodha for today**.
The authenticated frontend fetches the login URL with its dashboard CSRF token;
follow the normal Kite browser flow within ten minutes. The login response contains a random opaque state in `redirect_params`. PostgreSQL
stores only its SHA-256 hash, account/session binding and ten-minute expiry. The
callback verifies this one-time correlation and the registered callback location
without requiring browser cookies. Kite redirects to the registered URL;
`redirect_params` carries state and does not override that URL. Do not manually
paste callback tokens into terminal commands or logs. Direct unauthenticated
login initiation is rejected.

The callback exchanges the one-time request token using the documented SHA-256
checksum, then stores only a Fernet-encrypted access token. On first login,
`LOCAL_DEV` becomes the authenticated Kite `user_id`; future logins must match
that account. Do not rerun the development seed after binding a real account.
Zero or multiple account rows cause a safe configuration failure. No password,
PIN, TOTP, API secret, or request token is persisted. Tokens expire at 06:00 IST
on the next day; early provider invalidation also requires login again. A
`connected` status records the last successful login, not a real-time token check.

The following financial endpoints require a dashboard session; POST requests
also require the allowed Origin and X-CSRF-Token. Use the authenticated dashboard
for normal operation. Endpoint examples (bare curl receives 401):

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
Financial endpoints now require household dashboard authentication; keep local development bound to loopback. Errors use fixed messages and omit provider bodies and connection
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

`refresh_portfolio(db, if_stale=False)` is reusable by a future external scheduled job with a managed DB session. No scheduler or cron endpoint is added, and nothing is deployed. Day-only trade books require daily collection to build history. Keep local services bound to loopback; configure dashboard authentication before starting them.

Connection status adds local `token_valid`, backend `refresh_required` and `last_refresh_at`; early provider invalidation is detected on a read. Login always creates a persisted one-time correlation and returns to the dashboard after callback. The optional legacy `return_to_dashboard` parameter remains accepted. Destination comes solely from backend `DASHBOARD_URL` (HTTPS in production, HTTP loopback allowed locally), with no credentials/query/fragment. The local default is `http://127.0.0.1:5173/`. The ten-minute TTL, valid initiating session, atomic consumption and exact callback validation are enforced. Successful reconnect invalidates refresh freshness.

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
the access token expires; no password/PIN/TOTP automation is provided. The callback supports the Vercel/Railway cross-site topology without cookies.
Unrelated domains can still block the frontend's credentialed household login
request; same-site custom domains improve reliability of those API fetches. Check the callback in a real browser after eventual deployment.

Household session authentication protects financial endpoints. CORS remains a browser origin policy, not a substitute for authentication. Configure and verify the access boundary before public deployment.
Railway/proxy log retention must also exclude callback query strings; application
Uvicorn access logging already strips them. No settings/credentials are logged;
SQLAlchemy hides bound parameters and production debug tracebacks are disabled.
Investment endpoints remain brokerage read-only.

References: [Railway config](https://docs.railway.com/config-as-code/reference),
[monorepo roots](https://docs.railway.com/deployments/monorepo),
[pre-deploy migrations](https://docs.railway.com/deployments/pre-deploy-command),
[Uvicorn proxy trust](https://www.uvicorn.org/settings/).


## Household dashboard authentication

One household credential grants private dashboard access; Zerodha login separately
connects the brokerage data source. No household user-management system or trading
capability is introduced. There is no development bypass: missing/invalid auth
configuration prevents application startup in every environment.

Required backend variables (never `VITE_` variables): `DASHBOARD_USERNAME`,
`DASHBOARD_PASSWORD_HASH`, `SESSION_SECRET`, and optionally `SESSION_TTL_SECONDS`
(default 28800; range 300–86400). Keep `DATABASE_URL` configured. Generate the
password hash interactively from `apps/api` with the existing virtual environment:

```sh
python -m scripts.hash_dashboard_password
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

The first command prompts twice without echoing the password and prints only a
salted scrypt hash. The second prints an independent random session secret. Save
these values only in local gitignored `.env` or Railway secret variables. Do not
paste plaintext passwords into shell commands, source, reports or logs. Hashing
uses the existing cryptography package with scrypt N=131072, r=8, p=1 and a random
16-byte salt; no additional hashing dependency is needed. Each verification needs
approximately 128 MiB working memory, so provision a suitable Railway memory tier.

Apply `alembic upgrade head` locally before starting the updated API; production
uses the existing Railway pre-deploy command. Migration `0005_dashboard_auth`
adds only `dashboard_sessions` and `dashboard_login_attempts`, preserving portfolio,
trade, snapshot and brokerage credential tables. It has not been applied to the
local database as part of this task. Configure local credentials yourself, then
start the backend as documented and sign in through the dashboard. Use the same
127.0.0.1 hostname for frontend/backend/callback. Frontend requires no auth secrets.

API contracts:

- `POST /auth/login`: JSON username/password, requires an allowed `Origin`.
  Generic credential failure; no password/hash returned. A new authenticated
  session rotates/revokes the previous browser session.
- `GET /auth/session`: public normalized authenticated flag, and only for a valid
  session its expiration and CSRF token. Responses are not cached.
- `POST /auth/logout`: requires session, allowed Origin and `X-CSRF-Token`.
  Deletes the server session and clears the cookie; replay is rejected.
- `/health` and `/health/db` remain public. Existing development API documentation
  is unchanged. Every portfolio and Zerodha route requires a dashboard session.

Session cookies contain a random 256-bit opaque identifier and HMAC-SHA256
signature. PostgreSQL stores only a hash of the identifier, credential-version
fingerprint and absolute expiry. Password/username/session-secret rotation
invalidates prior sessions. Expired sessions are rejected server-side and pruned
on successful logins; there is no sliding refresh or localStorage bearer token.
CSRF tokens returned only to authenticated frontend code remain in memory. All
private POSTs and GET Zerodha login initiation require exact allowed Origin plus
this token. Brokerage callback uses a persisted hashed opaque correlation, ten-minute TTL
and exact callback URL checks, bound to the still-valid initiating dashboard
session. The callback itself does not require the dashboard cookie. If the session expires or is revoked during the
brokerage flow, sign in and restart the flow; callback validation is never bypassed.

Production cookie: `__Host-dashboard_session`, HttpOnly, Secure, SameSite=None,
Path=/, no Domain attribute. Development cookie: `dashboard_session`, HttpOnly,
SameSite=Lax on HTTP loopback. Production CORS permits only `FRONTEND_ORIGIN`,
credentials and the CSRF header. Use `fetch(credentials: include)` (already set).
Different HTTPS origins work when browser cookie policy permits them; default
Vercel and Railway domains are cross-site and third-party-cookie restrictions can
block cookies despite correct CORS. **For reliable deployment use same-site custom
origins, e.g. dashboard.example.com on Vercel and api.example.com on Railway.**
Brokerage callbacks use one-time database correlations and work independently of
third-party or partitioned cookies. No broad cookie domain is needed. Verify real browser
login/logout/callback in the final topology before public access. The frontend
checks that a successful login actually created a usable cookie and explains
cookie blocking when it did not. Do not weaken CSRF or cookie security to fix it.

Login windows persist in PostgreSQL and use row locks with consistent global/IP
lock order, so limits apply across instances: at most 10 attempts per IP and 30
for the household per 15-minute window, including successful attempts. Windows
reset after expiration; 429 includes Retry-After. Keys are HMAC hashes; no submitted
usernames, passwords, raw IPs or attempt event bodies are stored. A global window
prevents rotating-IP bypass but can temporarily deny the household after hostile
traffic. Verify trusted proxy addresses before using forwarded client IPs; never
trust arbitrary X-Forwarded-For headers. No Redis/in-memory-only limiter is used.
Expired attempt keys can be pruned operationally with a reviewed maintenance job
once their windows have elapsed; no in-process scheduler is added.

No secrets are logged. Login validation errors are sanitized so malformed bodies
cannot echo passwords. Private responses carry no-store/no-referrer headers;
callback query redaction remains. Production debug is off. Review infrastructure
logs as well and preserve the existing callback query exclusion.

References: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[MDN third-party cookies](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies).


## Cookie-independent Zerodha callback (migration 0006)

The authenticated, Origin/CSRF-checked `/integrations/zerodha/login` generates
256 random bits, returns the opaque value through Kite `redirect_params`, and
persists only SHA-256 of that value in `zerodha_login_states`. Its foreign keys
bind the configured account and initiating dashboard session; expiry is the
shorter of ten minutes and session expiry. No session/account identifier enters
the login URL. Logout deletes the session and cascades its correlations;
credential rotation and expired sessions are rejected when claiming state.

The callback locks/revalidates the session and atomically updates an unconsumed,
unexpired state with `UPDATE ... RETURNING`. That claim commits **before** any
external token exchange. Only one concurrent claimant can exchange; failed
exchanges, timeouts, crashes or token persistence failures require a new connect
attempt. Existing exchange validation, account identity checks and encrypted
credential storage remain intact. An account row lock serializes binding across
different login attempts. Logout/revocation before the claim blocks completion;
revocation after a committed claim cannot cancel an already-authorized exchange.
Expired rows remain until their session is deleted/pruned; no background cleanup
job or startup migration is introduced.

Success redirects with HTTP 303 to `DASHBOARD_URL?zerodha=connected`; ordinary
invalid/expired/replayed state and provider failures use `?zerodha=connect_failed`.
These markers contain no tokens or security details. Destination is server-only,
validated configuration, with no query/fragment/credentials. Responses are
`no-store` and `no-referrer`; logs contain fixed failure reason codes only.
Infrastructure access logs must also exclude the whole callback query string.
The frontend removes the marker while preserving other query parameters/hash,
checks household authentication, fetches brokerage status and performs one
controlled canonical portfolio refresh on successful connection. A forged marker
cannot connect an account or bypass household authentication.

After review and a separately authorized commit/push:

1. Railway pre-deploy command: `alembic upgrade head` from `apps/api`; verify
   `0006_zerodha_login_state` before switching backend traffic. The migration adds
   only a table/index, leaving existing financial/auth tables intact.
2. Deploy backend and redeploy the changed frontend.
3. Set `DASHBOARD_URL=https://familyinvestments.vercel.app`,
   `FRONTEND_ORIGIN=https://familyinvestments.vercel.app`, and
   `ZERODHA_REDIRECT_URL=https://familyinvestments-production.up.railway.app/integrations/zerodha/callback`.
   Register that exact redirect URL in Kite. Keep existing backend-only database,
   Zerodha, encryption and household auth secrets unchanged.
4. Preserve public HTTPS scheme/Host via trusted proxy forwarded headers using
   existing Railway/Uvicorn configuration; no new application middleware is needed.
5. Sign into the household dashboard, click **Connect Zerodha for today**, manually
   authenticate with Kite, verify Railway callback returns to Vercel, connection
   status is connected and canonical refresh completes. Reconnect manually when
   the daily access token expires. Verify logout and replay rejection as well.

No deployment or live brokerage authentication was performed by this change.
Actual Railway proxy behavior and browser cookie policy require this final live
check. If household cookies cannot be used for Vercel-to-Railway API fetches,
use same-site custom domains; the callback fix cannot override browser policy.
