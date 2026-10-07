# Family Investments dashboard

A local, read-only React + TypeScript dashboard for the existing FastAPI backend.

## Run locally

Use Node.js 22.12+ (validated with Node 26.8.2).

```sh
cd apps/web
npm ci
cp .env.example .env
npm run dev
```

Open http://127.0.0.1:5173. Start the backend from `apps/api` with the repository virtual environment:

```sh
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep both services bound to loopback. Dashboard session authentication is required; configure backend household credentials before starting. Local API configuration is optional `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`); never put provider secrets or backend configuration in a `VITE_` variable. Use the same `127.0.0.1` hostname for the frontend, API and configured Zerodha callback so browser-bound login cookies work consistently.

## Architecture

- `src/api`: explicit API response types, fetch helper, safe errors and login URL validation.
- `src/hooks`: query lifecycle with loading, errors and stale-response cleanup.
- `src/components`: metrics, P&L, states, Recharts history, monthly plan and allocation.
- `src/pages`: Overview, Portfolio, HoldingDetail, Investments and History.
- `src/utils`: Indian currency, quantities, signed percentages and India-time dates.
- `src/styles`: responsive plain CSS with desktop sidebar and compact mobile navigation.

Routes: `/`, `/portfolio`, `/portfolio/:symbol`, `/investments`, `/history`. Holding links retain exchange in a query parameter so distinct exchange histories are not merged.

Refresh calls the canonical `POST /portfolio/refresh`, then refetches the active page and connection status. A synchronous in-flight guard and disabled button prevent duplicate clicks. On app open, backend connection status permits one refresh only when the valid session has no full refresh within five minutes or on the current India date. The backend repeats the freshness check under its account lock. There is no polling.

Overview shows actual trade executions and compact order statuses. Portfolio keeps activity awaiting holdings separate from active holdings. Investments shows recorded delivery BUY amounts, explicitly incomplete before recorded trade history; no remaining/progress claim is made. Charges are unavailable when not supplied. Executions are never added again to holdings + cash.

Expired sessions show a persistent reconnect CTA. Login uses the existing cookie/state-protected callback and an optional backend-configured dashboard return. Browser credential automation is not used.

History ranges are calendar windows ending today in India. ALL is bounded by the API's 3,650-snapshot limit. Historical tables provide the precise data alongside charts. Actual allocation uses backend buckets unchanged; target percentages are derived from API target amounts. Day P&L is unavailable and contribution progress is not inferred.

## Checks

```sh
npm run build
npm run test
npm run typecheck
```

Vitest and React Testing Library cover formatting, safe API errors, response parsing, core overview metrics, unavailable day P&L, P&L colors, no holdings, disconnected/rejected sessions, canonical refresh, refetch, duplicate protection, one-shot automatic refresh, reconnect, actual activity and incomplete contributions. Financial fixtures exist only in test code and are excluded from the production bundle.

Backend bucket values are authoritative. UNCLASSIFIED displays as “Needs classification” in activity, holdings and allocation. Recorded purchases keep Other and Needs classification separate (including zero rows); unknown purchase values show an explicit classification warning. No frontend instrument heuristics exist.


## Private dashboard login

On app open, GET /auth/session must succeed before any financial requests or
Zerodha refresh. Unauthenticated users see the household username/password screen;
Zerodha connection remains a separate authenticated-dashboard control. Successful
login verifies the cookie via session check. Sign out revokes the backend session
and returns to login; expired private API sessions unmount financial pages.
Passwords clear after submission; login failures show fixed safe messages.

Configure DASHBOARD_USERNAME, DASHBOARD_PASSWORD_HASH, SESSION_SECRET and finite
SESSION_TTL_SECONDS only in the backend. Generate hashes with
`python -m scripts.hash_dashboard_password` from apps/api and follow the backend
README. No credentials or session bearer tokens belong in frontend env variables,
localStorage or source. The frontend keeps only the CSRF token in memory, sends
it on protected requests and uses fetch credentials: include. Development uses VITE_API_BASE_URL; production always uses /api.

For production, use Vercel Root Directory `apps/web`. `vercel.json` proxies
`/api/:path*` to `https://familyinvestments-production.up.railway.app/:path*`,
stripping the `/api` prefix without proxying static assets. Production always
uses `/api`, including when a legacy VITE_API_BASE_URL is set. Remove that
variable on the next separately authorized deployment. Never add backend secrets.

Keep FRONTEND_ORIGIN and DASHBOARD_URL at `https://familyinvestments.vercel.app`.
Keep Kite's registered callback and backend callback configuration at
`https://familyinvestments-production.up.railway.app/integrations/zerodha/callback`.
One-time callback state and the configured dashboard redirect are unchanged.

The host-only cookie becomes first-party to the browser's Vercel origin through
the proxy. Production retains Secure, HttpOnly, SameSite=None, Path=/, finite
Max-Age and the __Host- prefix without Domain. Development retains SameSite=Lax.
Session expiry, logout revocation, explicit origin checks and session-bound CSRF
verification are unchanged. The proxy must forward Cookie, Origin and
X-CSRF-Token and return Set-Cookie. Private responses already use no-store;
CORS remains explicitly scoped and direct Railway health checks are unaffected.

After a separately authorized deployment, verify mobile/in-app login, session,
portfolio, refresh, reconnect and logout through `/api`. Check the dashboard
cookie host, CSRF headers and rejected missing/invalid CSRF requests. Verify
Railway health and the unchanged one-time Zerodha callback/dashboard redirect.
Local tests cannot verify deployed Vercel cookie/header forwarding.
