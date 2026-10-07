# Phase 1 frontend implementation and validation

Implemented locally without deployment, commit or push. Backend business logic remains unchanged.

## Files created

Under `apps/web/`:

- `.env.example`, `README.md`, `index.html`, `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`
- `src/App.tsx`, `src/main.tsx`, `src/test-setup.ts`, `src/dashboard.test.tsx`
- `src/api/client.ts`, `src/api/types.ts`
- `src/hooks/useQuery.ts`
- `src/components/UI.tsx`, `src/components/Chart.tsx`, `src/components/Plan.tsx`
- `src/pages/Overview.tsx`, `src/pages/Portfolio.tsx`, `src/pages/HoldingDetail.tsx`, `src/pages/Investments.tsx`, `src/pages/History.tsx`
- `src/utils/format.ts`, `src/styles/global.css`

Also created `apps/api/tests/test_cors.py` and this report.

## Files modified

- `.gitignore`: ignores node_modules, dist and TypeScript build metadata.
- `apps/api/app/main.py`: development-only CORS for localhost and 127.0.0.1 on port 5173, GET/POST and explicit headers, credentials enabled for the existing login cookie. No wildcard origins. Production receives no added CORS middleware.

## Architecture, pages and components

React, TypeScript, Vite, React Router, Recharts and plain CSS. Typed API client uses only `VITE_API_BASE_URL`, a 20-second request timeout, normalized errors, encoded symbols and a strict HTTPS Kite login destination. Query hooks ignore stale results on navigation. Refresh is sequential and manually triggered.

Persistent shell includes connection status, last synced timestamp and Refresh. Shared components include Card, Metric, Pnl, State, Chart, Allocation and Plan. Responsive tables become holdings cards on mobile. Keyboard controls and visible focus states are implemented.

Routes and pages:

| Route | Page |
| --- | --- |
| `/` | Overview: account metrics, growth ranges, actual/target allocation and monthly plan |
| `/portfolio` | Holdings, symbol sorting and detail links |
| `/portfolio/:symbol` | Current metrics and history, exchange retained from holding links |
| `/investments` | Monthly plan and target allocation |
| `/history` | Switchable chart metric and snapshot table |

No daily P&L is invented. Single-point history has a history-building state. No contribution progress is inferred. Buckets remain exactly as provided by the API.

## Validation results

- Frontend: 11 Vitest/React Testing Library tests passed.
- Frontend production build passed; typecheck passed. Main app ~20 KB, vendor ~247 KB and charts ~363 KB before gzip; chunks are split without the original large-chunk warning.
- Backend: 119 tests passed, including two new CORS tests. Existing httpx/Starlette deprecation warning remains.
- Python compileall passed. `git diff --check` passed.
- Dependency installation audit after tooling updates: zero known vulnerabilities.
- Security inspection: zero configured backend credential values and zero backend secret variable names in the production bundle. Client configuration is only the public API URL. No credential imports, access tokens, encryption keys or database configuration are embedded. Test fixtures are not in the bundle.

## Live API and browser validation

Local API and frontend started on loopback ports 8000 and 5173. Holdings (10 real rows), ETERNAL holding detail/history, monthly targets and snapshot history rendered using real API responses. One historical snapshot correctly produces the history-building chart state. Connected status rendered from the API initially.

The current provider session is rejected: summary and live holdings sync return HTTP 401 despite the saved status saying connected. The app displays a reconnect prompt and overrides that stale connected indicator. Live refresh was exercised and stops before snapshot creation on sync failure. Successful sync → snapshot → refetch is covered by tests; successful live refresh and the hero/actual-allocation live view remain unverified until the user reconnects Zerodha. No authentication credentials were entered or changed.

Inspected desktop/tablet/mobile layouts at 1440, 1024, 768 and 390 pixels. Document width matched viewport width at each size with no page-wide overflow; tables scroll internally and mobile holdings stack. Investments and History were visually inspected on mobile, and desktop/tablet Overview was inspected in its real session-expired state. Live hero metric layout could not be visually verified while summary is unavailable.

Final reloaded browser session produced no console errors or warnings. During dependency replacement, temporary Vite HMR/React errors occurred; these disappeared after restart and reload. Backend request logs showed the intended requests; only the provider-session 401 responses failed. No continuous polling or unintended mutation requests were observed.

## Git evidence

`git diff --stat` (tracked files only; new frontend files are untracked):

```text
 .gitignore           |  3 +++
 apps/api/app/main.py | 10 ++++++++++
 2 files changed, 13 insertions(+)
```

`git status --short`:

```text
 M .gitignore
 M apps/api/app/main.py
?? apps/api/tests/test_cors.py
?? apps/web/
?? docs/
```
