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

Keep both services bound to loopback. No dashboard authentication is implemented in this phase. The only client configuration is `VITE_API_BASE_URL`; never put provider secrets or backend configuration in a `VITE_` variable. Use the same `127.0.0.1` hostname for the frontend, API and configured Zerodha callback so browser-bound login cookies work consistently.

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
