# Current investment state implementation and validation

Completed 7 October 2026. All brokerage operations remain read-only. Values reflect the latest live validation and may change with prices/cash.

## 1. Root cause

Sync upserted account/exchange/symbol identities but did not retire absent identities. Six old exchange rows continued contributing to current totals.

## 2. Holdings lifecycle

Migration 0002 adds is_active. A validated complete response activates returned identities and deactivates absent identities atomically under an account lock. All 16 physical rows remain; failed/malformed responses and persistence failures cannot change membership. Current holdings, allocations, summary and current snapshots filter active rows. Earlier dates remain historical.

## 3. Orders sync

The existing Kite client adds GET /orders. Canonical refresh upserts existing orders by provider identity, retains exact status, requested/filled quantities, exchange, product and timestamps. book_date distinguishes today’s book from older placement context. No brokerage write exists.

## 4. Trade sync

GET /trades provides execution-level persistence in the existing investment_transactions table. Identity includes account/date/exchange/provider order/trade IDs, supporting multiple fills and safe repeated sync. Immutable replay conflicts fail. Decimal/Numeric amounts avoid float persistence; unknown charges/net amounts are null.

## 5. Awaiting holdings

Overview shows real executions; Portfolio shows a separate awaiting card. Missing/insufficient matching active holding quantity gives AWAITING_HOLDINGS. Existing quantity is only HOLDING_PRESENT_UNCONFIRMED, never proof of settlement. Same-day buys offset by sells are NETTED_BY_SELLS. SELL/non-CNC events are NOT_APPLICABLE. Executions never inflate holdings + cash or snapshots.

## 6. NIFTYBEES live result

NSE CNC BUY 2 at ₹258.59, ₹517.18 gross, executed 09:15 IST on 7 October 2026. Provider trade confirmed execution. NIFTY_50 classification. Not in active holdings, therefore AWAITING_HOLDINGS. No fake holding inserted. The live order book timestamp was today; older order IDs are retained without inferring placement date from their text.

## 7. Monthly contributions

Recorded CNC BUY purchases total ₹1,953.54: Nifty ₹517.18, midcap ₹896.00, OTHER ₹540.36. Collection begins 7 October; history_complete=false. No complete month progress/remaining claim. SELL, unfilled/rejected/cancelled orders without fills, intraday trades and legacy records without provider identity are excluded. Target remains ₹15,000 (₹8,000/₹5,000/₹2,000).

## 8. Canonical refresh

POST /portfolio/refresh validates local token, fetches and validates holdings, orders, trades and funds before writes, prevents midnight date crossover, then atomically reconciles holdings, upserts books/fills, upserts today’s snapshot and records last_refresh_at. A single commit; all failures rollback. Frontend calls only this endpoint. GET activity and contributions serve normalized persisted data.

## 9. Reconnect UX

Expired stored token or provider auth rejection produces reconnect_required, persistent friendly expired banner and Connect Zerodha for today. Summary requests wait for a locally valid connected status. Reconnect retains HttpOnly encrypted state, TTL, exact callback checks; optional 303 dashboard return uses backend-only validated DASHBOARD_URL. Tests cover redirect security. No live logout or credential automation was performed.

## 10. Scheduler foundation

No existing scheduler found. refresh_portfolio(db, if_stale=False) is independent of HTTP and reusable with a managed DB session by a future external job. No in-process scheduler, cron endpoint or deployment. App-open performs one controlled refresh with backend five-minute/current-India-date freshness guard; no polling. Button guards concurrent clicks.

## 11. Files created

Full untracked file inventory below includes the preserved Phase 1 frontend and previous lifecycle work, not only files newly created in this request.

- `apps/api/alembic/versions/0002_holding_lifecycle.py`
- `apps/api/alembic/versions/0003_execution_activity.py`
- `apps/api/app/integrations/zerodha/activity_schemas.py`
- `apps/api/app/portfolio/activity.py`
- `apps/api/app/portfolio/activity_schemas.py`
- `apps/api/tests/test_activity.py`
- `apps/api/tests/test_cors.py`
- `apps/web/.env.example`
- `apps/web/README.md`
- `apps/web/index.html`
- `apps/web/package-lock.json`
- `apps/web/package.json`
- `apps/web/src/App.tsx`
- `apps/web/src/api/client.ts`
- `apps/web/src/api/types.ts`
- `apps/web/src/components/ActivityCard.tsx`
- `apps/web/src/components/Chart.tsx`
- `apps/web/src/components/Plan.tsx`
- `apps/web/src/components/RecordedContributions.tsx`
- `apps/web/src/components/UI.tsx`
- `apps/web/src/dashboard.test.tsx`
- `apps/web/src/hooks/useQuery.ts`
- `apps/web/src/main.tsx`
- `apps/web/src/pages/History.tsx`
- `apps/web/src/pages/HoldingDetail.tsx`
- `apps/web/src/pages/Investments.tsx`
- `apps/web/src/pages/Overview.tsx`
- `apps/web/src/pages/Portfolio.tsx`
- `apps/web/src/styles/global.css`
- `apps/web/src/test-setup.ts`
- `apps/web/src/utils/format.ts`
- `apps/web/tsconfig.json`
- `apps/web/vite.config.ts`
- `docs/frontend-phase1.md`
- `docs/current-investment-state.md` (this report)

## 12. Files modified

Tracked modifications below include preserved earlier work.

- `.gitignore`
- `apps/api/.env.example`
- `apps/api/README.md`
- `apps/api/app/config.py`
- `apps/api/app/integrations/zerodha/client.py`
- `apps/api/app/integrations/zerodha/routes.py`
- `apps/api/app/integrations/zerodha/schemas.py`
- `apps/api/app/integrations/zerodha/service.py`
- `apps/api/app/main.py`
- `apps/api/app/models/account.py`
- `apps/api/app/models/order.py`
- `apps/api/app/models/portfolio.py`
- `apps/api/app/portfolio/routes.py`
- `apps/api/app/portfolio/service.py`
- `apps/api/tests/test_portfolio.py`
- `apps/api/tests/test_schema.py`
- `apps/api/tests/test_zerodha.py`

Existing untracked Phase 1 files extended in this request: apps/web/README.md; src/App.tsx; src/api/client.ts and types.ts; src/hooks/useQuery.ts; src/components/UI.tsx and Plan.tsx; src/pages/Overview.tsx, Portfolio.tsx, Investments.tsx and History.tsx; src/styles/global.css; src/dashboard.test.tsx.

## 13. Migrations

0002_holding_lifecycle (previous completed lifecycle fix) and new 0003_execution_activity. New head adds account freshness, order book date, execution identity/context and nullable unknown charges/net amounts. Applied migrations were not edited. Local PostgreSQL was upgraded, not recreated. Downgrade deliberately fails if null unknown amounts cannot satisfy older NOT NULL columns.

## 14. Tests added

Lifecycle coverage preserves successful/failed reconciliation, exchange changes, active filtering, atomic rollback and physical preservation. Execution/refresh coverage adds idempotence, multiple fills, partial/cancelled/rejected statuses, BUY/SELL, classification, conservative attribution, no double count, unknown charges, conflicting replay, scoped identity, fresh guard, failed fetch/write/commit rollback and same-day buy/sell offsets. Auth/client tests cover local expiry, safe dashboard redirect and read-only methods. Frontend tests cover actual activity, incomplete contributions, canonical refresh, one-shot auto refresh, duplicate clicks and reconnect.

## 15. Backend tests

python -m pytest -q: 165 passed (29 more cases than the prior 136-test lifecycle baseline). One existing Starlette/httpx deprecation warning. python -m compileall -q app tests passed; migration compilation passed. Tests use isolated/mocked data, no brokerage trading.

## 16. Frontend tests

npm run test: 17 passed. Financial fixtures remain test-only.

## 17. Build

npm run build passed. Application chunk 24.88 kB; vendor 246.95 kB; charts 362.94 kB. Production bundle inspected.

## 18. Typecheck

npm run typecheck passed.

## 19. Migration current/head

alembic current and alembic heads both report 0003_execution_activity (head).

## 20. Live holdings

10 active holdings from the complete provider response. 16 physical rows retained, 6 inactive. NIFTYBEES remains absent from holdings and visible through actual execution data.

## 21. Live summary

Latest canonical refresh 7 October 2026 09:49 IST: invested ₹7585.4696; holdings market ₹8880.9800; available cash ₹3099.66; holdings + cash ₹11980.6400; P&L ₹1295.5104 (17.078842%). Count 10. Current holding allocation is OTHER ₹8,880.98; activity classifications are separate. Cash normalization priority live_balance → net → available.cash remains unchanged.

## 22. Today’s activity

Three actual CNC BUY executions, all awaiting holdings: NIFTYBEES 2 × ₹258.59 = ₹517.18 at 09:15; MIDCAPETF 40 × ₹22.40 = ₹896.00 at 09:37:07; HDFCSML250 3 × ₹180.12 = ₹540.36 at 09:37:58. Three COMPLETE orders, zero open/pending, zero rejected/cancelled. Three stored provider fills after repeated refresh; no duplicates. Unknown HDFCSML250 mapping stays OTHER.

## 23. Corrected snapshot

2026-10-07 snapshot now has invested ₹7,585.4696, holdings ₹8,880.98, cash ₹3,099.66, total ₹11,980.64 and P&L ₹1,295.5104. Exactly one portfolio snapshot for today; original ID/account/created_at preserved. SHA-256 row-content comparison confirms earlier portfolio snapshot (1 row) and holding snapshots (10 rows) unchanged.

## 24. Responsive validation

Overview, Portfolio, Investments, History and ETERNAL detail checked at 1440, 1024, 768 and 390 pixels (20 combinations). Document scroll width equals client width in every combination: no page-wide overflow. Activity/awaiting cards and contributions visually inspected, desktop/tablet/mobile layouts retained. Existing loading/empty/error and reconnect states covered by frontend tests; valid live session retained.

## 25. Console/network

Browser error/warning console empty after validation. Live refresh and all requested portfolio reads returned success, no unintended failed requests observed in local server output. Manual UI refresh visibly disabled while running then showed Portfolio refreshed successfully. Freshness endpoint skipped repeat provider reads. Temporary viewport override reset; user tab left on Overview.

## 26. Security

Production bundle scan compared actual configured API key, API secret, encryption key, database URL and decrypted stored access token without printing values: all absent. Only POST routes are local holdings sync, snapshot and canonical refresh. No PUT/PATCH/DELETE/order mutation routes. No password/PIN/TOTP persistence or new credential fields. Existing encrypted access-token storage and sanitized errors retained. No automated login, orders, sales, rebalancing or F&O execution.

## 27. git diff --stat

Tracked-only output (untracked files are not included):

```text
 .gitignore                                   |   3 +
 apps/api/.env.example                        |   3 +
 apps/api/README.md                           |  47 ++++++--
 apps/api/app/config.py                       |   1 +
 apps/api/app/integrations/zerodha/client.py  |  10 ++
 apps/api/app/integrations/zerodha/routes.py  |  47 ++++++--
 apps/api/app/integrations/zerodha/schemas.py |   3 +
 apps/api/app/integrations/zerodha/service.py |  53 +++++++--
 apps/api/app/main.py                         |  10 ++
 apps/api/app/models/account.py               |   1 +
 apps/api/app/models/order.py                 |  21 +++-
 apps/api/app/models/portfolio.py             |   3 +-
 apps/api/app/portfolio/routes.py             |  19 +++
 apps/api/app/portfolio/service.py            |  10 +-
 apps/api/tests/test_portfolio.py             |  51 ++++++++
 apps/api/tests/test_schema.py                |  28 ++++-
 apps/api/tests/test_zerodha.py               | 167 +++++++++++++++++++++++++--
 17 files changed, 428 insertions(+), 49 deletions(-)
```

## 28. git status --short

Captured before adding this report; docs/ is already untracked. Nothing staged, committed or pushed.

```text
 M .gitignore
 M apps/api/.env.example
 M apps/api/README.md
 M apps/api/app/config.py
 M apps/api/app/integrations/zerodha/client.py
 M apps/api/app/integrations/zerodha/routes.py
 M apps/api/app/integrations/zerodha/schemas.py
 M apps/api/app/integrations/zerodha/service.py
 M apps/api/app/main.py
 M apps/api/app/models/account.py
 M apps/api/app/models/order.py
 M apps/api/app/models/portfolio.py
 M apps/api/app/portfolio/routes.py
 M apps/api/app/portfolio/service.py
 M apps/api/tests/test_portfolio.py
 M apps/api/tests/test_schema.py
 M apps/api/tests/test_zerodha.py
?? apps/api/alembic/versions/0002_holding_lifecycle.py
?? apps/api/alembic/versions/0003_execution_activity.py
?? apps/api/app/integrations/zerodha/activity_schemas.py
?? apps/api/app/portfolio/activity.py
?? apps/api/app/portfolio/activity_schemas.py
?? apps/api/tests/test_activity.py
?? apps/api/tests/test_cors.py
?? apps/web/
?? docs/
```

## 29. Known limitations

Orders/trades are day-only sources; missed collection days cannot be reconstructed here. Recorded monthly purchases are incomplete, not net external deposits. Holdings quantity cannot attribute old inventory to today’s fills; sufficient quantity stays unconfirmed. Positions are not used because they do not establish safe long-term settlement attribution. Total is explicitly holdings + cash and omits a separately valued pending-execution portfolio component. Charges/net execution costs and day P&L remain unavailable. No automatic scheduled collection/deployment yet; local services have no dashboard authentication and remain loopback-only. Provider invalidation before known expiry is detected during reads. Valid complete provider payloads rely on the endpoint’s completeness contract; arbitrary silent provider truncation cannot be detected from a syntactically valid list.

## 30. Next step

Review this uncommitted baseline, then add authenticated deployment/access controls and an external daily refresh job that alerts only on reconnect or failure. Collect reliable daily executions before presenting full monthly progress; separately choose and explicitly map the intended small-cap ETF. No deployment or commit performed.

Semantics checked against [official Kite order/trade documentation](https://kite.trade/docs/connect/v3/orders/) and [holdings documentation](https://kite.trade/docs/connect/v3/portfolio/).
