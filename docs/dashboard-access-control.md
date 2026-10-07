# Household dashboard access-control report

Completed 7 October 2026. Authentication implementation and tests are complete; private credential configuration and local migration remain operator steps.

## 1. Authentication architecture

One environment-configured household credential, independent of the Zerodha account. Existing cryptography provides fixed-cost scrypt (N=131072, r=8, p=1, random 16-byte salt). Password hashes and session secret use SecretStr configuration. No plaintext password persistence or development bypass. Startup refuses missing/invalid auth configuration or an unconfigured database. No extra dependencies.

## 2. Session approach

Random 256-bit opaque ID plus HMAC-SHA256 signature in an HttpOnly cookie. Database stores the identifier hash, credential-version fingerprint and absolute expiry. Session is revocable: logout deletes its row, and password/username/session-secret rotation invalidates old cookies. Eight-hour default, configurable 300–86400 seconds. This supports finite server-side sessions and immediate logout revocation without localStorage tokens. CSRF token returned to authenticated frontend is held only in memory.

## 3. Protected routes

Every route under /portfolio/ and /integrations/zerodha/ carries the shared require_access dependency, including GET reads, POST refresh/sync/snapshot, brokerage login initiation and callback. Protected writes and GET brokerage login initiation require exact allowed Origin and X-CSRF-Token. Unauthenticated requests return normalized dashboard-auth-required 401. Database outages fail closed. No order placement/modification/cancellation route was introduced.

## 4. Public routes

GET /health and GET /health/db retain existing contracts. POST /auth/login and GET /auth/session are public bootstrap endpoints. POST /auth/logout requires session and CSRF. Existing API documentation routes remain unchanged; they expose schema, not financial data. Login requires allowed Origin and gives generic errors. Session response reveals no identifier/password/hash and returns expiry/CSRF only when authenticated.

## 5. Environment

Added DASHBOARD_USERNAME, DASHBOARD_PASSWORD_HASH, SESSION_SECRET, SESSION_TTL_SECONDS (default 28800). Existing DATABASE_URL, APP_ENV, FRONTEND_ORIGIN, DASHBOARD_URL and brokerage/encryption variables remain required as previously documented. Password hash generation is interactive: python -m scripts.hash_dashboard_password. Generate an independent random session secret locally with the documented secrets.token_urlsafe command. No real credentials were generated or written to .env by this task.

## 6. Cookies/CORS

Production: __Host-dashboard_session, Secure, HttpOnly, SameSite=None, Path=/, no Domain. Development: dashboard_session, HttpOnly, SameSite=Lax on loopback. CORS still allows one explicit production frontend origin with credentials; X-CSRF-Token is now allowed. Frontend uses credentials: include and refuses HTTP auth transport from an HTTPS page. No broad cookie domain or wildcard origin. Same-site custom frontend/API domains are recommended because browsers may block cross-site provider-domain cookies.

## 7. Login rate limits

PostgreSQL attempt windows, not process memory: 10 attempts per IP and 30 household-wide per 15 minutes, including successful attempts. Consistent global-then-IP row locks serialize counters across instances and bound simultaneous scrypt verification. Global limit blocks rotating-IP/username bypass and checks budget before creating new IP keys. Only HMAC keys/counters/window timestamps persist, never raw IPs, submitted usernames or passwords. Temporary 429 includes Retry-After. Global lockout can temporarily affect the household under attack; expired IP keys need operational pruning later.

## 8. Zerodha callback

Brokerage login initiation requires dashboard authentication and CSRF. Existing encrypted state now also carries the dashboard session hash. Callback requires that same still-valid household session and retains existing HttpOnly state cookie, nonce, TTL, exact public callback URL and encryption checks. It remains a top-level GET requiring brokerage state rather than application POST CSRF headers. Logout/re-login, expired dashboard sessions or mismatched sessions reject the old flow. No brokerage credentials or automated login were added.

## 9. Frontend UX

App checks household session before mounting financial pages or performing automatic brokerage refresh. Minimal login screen follows existing palette/type, clears password after submission and gives safe errors. Successful login verifies a usable cookie with GET session before mounting. Sign out revokes session and returns to login. Absolute expiry or private API 401 unmounts the dashboard; brokerage token expiry still shows a distinct Connect Zerodha for today CTA. Header wraps authentication controls on narrow screens. Login visually inspected at 1440/1024/768/390: no overflow.

## 10. Files changed

Modified:

- `apps/api/.env.example`
- `apps/api/README.md`
- `apps/api/app/config.py`
- `apps/api/app/integrations/zerodha/routes.py`
- `apps/api/app/main.py`
- `apps/api/app/models/__init__.py`
- `apps/api/tests/test_activity.py`
- `apps/api/tests/test_cors.py`
- `apps/api/tests/test_portfolio.py`
- `apps/api/tests/test_schema.py`
- `apps/api/tests/test_zerodha.py`
- `apps/web/README.md`
- `apps/web/src/App.tsx`
- `apps/web/src/api/client.ts`
- `apps/web/src/dashboard.test.tsx`
- `apps/web/src/styles/global.css`

Created:

- `apps/api/alembic/versions/0005_dashboard_auth.py`
- `apps/api/app/auth/__init__.py`
- `apps/api/app/auth/passwords.py`
- `apps/api/app/auth/routes.py`
- `apps/api/app/auth/service.py`
- `apps/api/app/models/auth.py`
- `apps/api/scripts/hash_dashboard_password.py`
- `apps/api/tests/test_auth.py`
- `apps/web/src/api/auth.ts`
- `apps/web/src/auth.test.tsx`
- `apps/web/src/components/Login.tsx`
- `docs/dashboard-access-control.md`

## 11. Migration

0005_dashboard_auth adds dashboard_sessions and dashboard_login_attempts only. Existing revisions and financial/brokerage tables are unchanged. Frozen migration-to-model metadata test covers all five revisions, uniqueness and expiry index. Alembic heads reports 0005_dashboard_auth (head). Local PostgreSQL was not migrated during this task; apply alembic upgrade head after setting up credentials. Railway already runs that command in pre-deploy. No deployment performed.

## 12. Backend validation

212 tests passed, including 23 new authentication cases. Existing domain tests explicitly override only the access dependency so their brokerage/accounting behavior remains isolated; new auth tests exercise the real boundary. Coverage: public health, private-route denial, valid/invalid login, cookie flags, session status, logout replay rejection, expiry, malformed/tampered cookies, credential rotation, origin/CSRF, persisted IP/global limits across clients, startup missing config, callback/session binding, no credential logs/storage and all-private-route dependency inspection. Full suite also passed with DATABASE_URL empty, proving no live database is required. One existing Starlette/httpx deprecation warning. compileall app/tests and migration py_compile passed.

## 13. Frontend validation

26 tests passed (seven added): unauthenticated login/no financial fetches, valid session and distinct brokerage reconnect, successful login cookie check, generic failed login/password clearing, logout, private session expiry and HTTPS transport enforcement. Existing 19 dashboard tests retained with authenticated session fixtures and correct distinction between household vs brokerage 401.

## 14. Build/typecheck

npm run typecheck and npm run build passed. Application JS 29.26 kB, existing vendor 246.95 kB and charts 362.94 kB. No auth credentials enter VITE config or the bundle. Temporary browser viewport reset.

## 15. Security validation

Final bundle compared against configured API key/secret, database URL, token encryption key and decrypted stored brokerage access token without printing values: none present. Configured auth hashes/secrets were also included if present; local auth remains unconfigured. Test auth secrets/passwords absent from bundle. Login validation errors do not echo password inputs; caplog test confirms login emits neither password nor cookie. Cookie/session raw ID is not persisted. Every private route is guarded and unauthenticated denial tested. Uvicorn callback query redaction, token encryption, cash normalization, trade identity and read-only routes remain unchanged. Old pre-auth local backend was stopped; launching updated source exited with sanitized missing-auth configuration error (fail closed). No public service was deployed.

## 16. git diff --stat

Tracked files only; newly created auth code/tests/migration/report are not included:

```text
 apps/api/.env.example                       |   9 +++
 apps/api/README.md                          | 119 +++++++++++++++++++++++++---
 apps/api/app/config.py                      |   4 +
 apps/api/app/integrations/zerodha/routes.py |   9 ++-
 apps/api/app/main.py                        |  40 ++++++++--
 apps/api/app/models/__init__.py             |   2 +
 apps/api/tests/test_activity.py             |   3 +
 apps/api/tests/test_cors.py                 |   2 +
 apps/api/tests/test_portfolio.py            |   3 +
 apps/api/tests/test_schema.py               |   8 +-
 apps/api/tests/test_zerodha.py              |   8 +-
 apps/web/README.md                          |  27 ++++++-
 apps/web/src/App.tsx                        |  34 +++++++-
 apps/web/src/api/client.ts                  |  24 +++---
 apps/web/src/dashboard.test.tsx             |   6 +-
 apps/web/src/styles/global.css              |  13 +++
 16 files changed, 274 insertions(+), 37 deletions(-)
```

git diff --check passed.

## 17. git status --short

Snapshot includes this report. No staging/commit/push:

```text
 M apps/api/.env.example
 M apps/api/README.md
 M apps/api/app/config.py
 M apps/api/app/integrations/zerodha/routes.py
 M apps/api/app/main.py
 M apps/api/app/models/__init__.py
 M apps/api/tests/test_activity.py
 M apps/api/tests/test_cors.py
 M apps/api/tests/test_portfolio.py
 M apps/api/tests/test_schema.py
 M apps/api/tests/test_zerodha.py
 M apps/web/README.md
 M apps/web/src/App.tsx
 M apps/web/src/api/client.ts
 M apps/web/src/dashboard.test.tsx
 M apps/web/src/styles/global.css
?? apps/api/alembic/versions/0005_dashboard_auth.py
?? apps/api/app/auth/
?? apps/api/app/models/auth.py
?? apps/api/scripts/hash_dashboard_password.py
?? apps/api/tests/test_auth.py
?? apps/web/src/api/auth.ts
?? apps/web/src/auth.test.tsx
?? apps/web/src/components/Login.tsx
?? docs/dashboard-access-control.md
```

## 18. Deployment notes and remaining setup

Backend is currently stopped intentionally because household auth configuration is absent. Leave the old unauthenticated process stopped. Privately set the household username, interactive password hash and independent session secret; apply alembic upgrade head locally, then restart. No local .env values or financial data were changed. For eventual Railway/Vercel deployment, configure HTTPS API/frontend same-site custom domains, exact FRONTEND_ORIGIN, DASHBOARD_URL and registered Kite redirect; share auth config across replicas and verify trusted ingress proxies for callback scheme and IP limits. Verify real browser login/logout/callback on that topology before public access. Default provider domains may fail due to third-party-cookie policy even with correct CORS; no security bypass or long-lived bearer storage was added. Scrypt needs about 128 MiB working memory; provision a suitable Railway memory tier. Live PostgreSQL multi-instance load testing and production browser topology validation were not performed. Auth tests use isolated SQLite storage; PostgreSQL lock/uniqueness semantics are implemented and migration DDL checked. Brokerage authentication remains manual when expired. No Redis, user-management system, scheduler, trading, deployment, commit or push.

Sources: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [MDN cookie restrictions](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies).
