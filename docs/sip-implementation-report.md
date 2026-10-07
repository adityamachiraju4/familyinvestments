# SIP / mutual-fund implementation report

Implemented locally. No commit, push, deployment, live migration, brokerage mutation,
Groww scraping, credentials, or fabricated production holdings.

1. **SIP architecture:** dated ACTIVE/PAUSED/STOPPED instructions, monthly amount,
   schedule day, provider source and scheme reference. One existing authenticated
   household; independent MF accounts represent its members.
2. **Mutual funds:** separate authoritative scheme/folio identity, category, source
   transactions and dated current holdings. Actual scheme metrics are explicitly
   labelled where multiple SIPs share one scheme.
3. **Persistence:** five tables: mutual_fund_accounts, mutual_fund_schemes, sips,
   mutual_fund_transactions, mutual_fund_holdings. Decimal money, optional units/NAV,
   unique event identity, enum/status/date/amount constraints. No seed data.
4. **Projection method:** Decimal recurrence, monthly nominal annual rate / 12,
   end-of-month contributions, start/end dates respected. Current corpus compounds;
   future contributions and growth reconcile to corpus. Missing valuations are
   flagged. Scheme corpus is proportionally allocated across active SIPs, counted
   once in combined figures. All MF corpus is included in the combined view.
5. **Scenarios:** backend-owned Conservative 8%, Base 10%, Optimistic 12%; custom
   rates validated to 0–30%. UI uses “Illustrative return assumption” and disclosure.
6. **XIRR:** date-aware ACT/365 Decimal bisection, 200 iterations, conventional
   cashflows only; complete verified history and terminal valuations required.
   Missing/ambiguous/nonconvergent histories return Unavailable. Gain/loss uses
   verified remaining cost basis and excludes claims about lifetime realized profit.
7. **Combined family:** family_composition is a domain composition boundary for
   settled Stocks & ETFs + actual Mutual Funds + available Cash. Unknown components
   leave total unavailable. No MIS turnover, positions or delivery double counting.
   This prepares architecture; the existing overview is not replaced.
8. **Monthly contributions:** original Zerodha CNC BUY amounts unchanged; confirmed
   MF PURCHASE/SIP records added separately and in combined recorded total.
   Redemptions, switches, cancelled/pending transactions and MIS excluded.
9. **Frontend:** overview, per-SIP scheme actuals, configured scenario selector,
   1Y/5Y/10Y contribution/growth/corpus rows, “At your current SIP pace” card,
   two-series Year 0–10 chart. Float conversion occurs only for chart rendering.
10. **Empty state:** “No SIPs imported yet.” Describes future verified CAS/statement
    ingestion. No active import or trading controls are offered.
11. **Files:** see Git inventory below and docs/mutual-funds.md for methodology.
12. **Migration:** 0007_mutual_funds follows 0006_zerodha_login_state. One Alembic
    head; old migrations unchanged. Migration/model DDL consistency and PostgreSQL
    offline upgrade/downgrade validated by tests. No live database migration run.
13. **Backend:** python -m pytest -q: 368 passed; one existing Starlette/httpx
    deprecation warning. python -m compileall -q app tests: passed. alembic heads:
    0007_mutual_funds (head). New tests include projections, status/date exclusion,
    Decimal reconciliation, XIRR, import replay/conflicts, invalid money/rates,
    authenticated GET routes, mutation rejection and migration consistency.
14. **Frontend:** npm run test: 40 tests passed in four files; empty state,
    horizons, combined card, scenario switch, disclosure and absence of trading
    controls covered, existing tests preserved.
15. **Build/typecheck:** npm run typecheck and npm run build passed.
16. **Security:** real household-session rejection tests cover all three new
    endpoints; GET only with no-store headers. Trusted internal statement boundary
    has no credentials or networking. No secrets added. No financial broker writes.
    git diff --check passed. Import is not exposed through HTTP; provider-switch
    reconciliation and reviewed ingestion UI are future work.
17. **git diff --stat:** below (Git excludes untracked additions from this command).
18. **git status --short:** below; all changes remain uncommitted.
19. **Data needed next:** verified household account/member mapping, scheme/plan/
    option/folio/ISIN identities, authoritative categories, real SIP schedules and
    statuses, complete dated transactions with stable provider event IDs, amounts,
    optional units/NAV, current dated valuations and remaining cost basis. Verify
    completeness and reconcile sources before enabling XIRR or importing overlaps.

## Git inventory

```text
 apps/api/app/main.py                              |  5 +++-
 apps/api/app/models/__init__.py                   |  2 ++
 apps/api/app/portfolio/activity.py                |  5 +++-
 apps/api/app/portfolio/activity_schemas.py        |  2 ++
 apps/api/tests/test_activity.py                   |  3 +++
 apps/api/tests/test_auth.py                       |  2 +-
 apps/api/tests/test_schema.py                     |  4 +--
 apps/web/src/api/types.ts                         |  2 ++
 apps/web/src/components/RecordedContributions.tsx | 30 ++++++++++++++++++++---
 apps/web/src/pages/Investments.tsx                |  2 ++
 apps/web/src/styles/global.css                    | 22 +++++++++++++++++
 11 files changed, 71 insertions(+), 8 deletions(-)
```

```text
 M apps/api/app/main.py
 M apps/api/app/models/__init__.py
 M apps/api/app/portfolio/activity.py
 M apps/api/app/portfolio/activity_schemas.py
 M apps/api/tests/test_activity.py
 M apps/api/tests/test_auth.py
 M apps/api/tests/test_schema.py
 M apps/web/src/api/types.ts
 M apps/web/src/components/RecordedContributions.tsx
 M apps/web/src/pages/Investments.tsx
 M apps/web/src/styles/global.css
?? apps/api/alembic/versions/0007_mutual_funds.py
?? apps/api/app/investments/
?? apps/api/app/models/mutual_fund.py
?? apps/api/tests/test_investments.py
?? apps/web/src/api/investments.ts
?? apps/web/src/components/SIPPlanning.tsx
?? apps/web/src/sips.test.tsx
?? docs/mutual-funds.md
?? docs/sip-implementation-report.md
```

New files (expanded):

```text
apps/api/alembic/versions/0007_mutual_funds.py
apps/api/app/investments/__init__.py
apps/api/app/investments/calculations.py
apps/api/app/investments/imports.py
apps/api/app/investments/routes.py
apps/api/app/investments/service.py
apps/api/app/models/mutual_fund.py
apps/api/tests/test_investments.py
apps/web/src/api/investments.ts
apps/web/src/components/SIPPlanning.tsx
apps/web/src/sips.test.tsx
docs/mutual-funds.md
docs/sip-implementation-report.md
```
