# Household SIP and mutual-fund planning

The dashboard remains read-only. No Groww credentials, private API access, scraping,
trading, or import mutation endpoint is introduced. No production records are seeded.
All new endpoints require the existing household session and send no-store headers.
The present app is one household, not a multi-tenant system. Mutual-fund accounts
represent members; they are deliberately independent of Zerodha accounts.

A SIP is an instruction, not evidence that money was invested. Scheme/folio records
hold authoritative category, plan, option and optional ISIN. Categories default to
UNCLASSIFIED and are never guessed from names. SIP instructions carry source,
monthly amount, dates, status and payment day. Transactions are separate immutable
confirmed/pending/cancelled events. Current holdings have their own dated valuation,
units, NAV and optional verified invested cost. Current values never use projections.
Gain/loss is current value minus verified invested cost (unavailable without cost),
not lifetime realized profit. Recorded contributions may be incomplete.

Sources are GROWW, CAS and MANUAL. `StatementProvider` is an internal trusted adapter
boundary, without networking. A future CAS/supported-statement parser must verify
account, scheme/plan/folio identity, source, amounts, currencies and event IDs before
calling `import_transactions`. Each source event has a stable key scoped to scheme;
files and row positions are not identities. Exact replays are ignored; changed
immutable events are rejected. A database uniqueness constraint handles concurrent
replays by rejecting the duplicate transaction; the caller rolls back/retries the
whole import. Provider switches need identity reconciliation before importing the
same events from a second source. Automatic cross-source deduplication is not claimed.

XIRR uses negative purchases/SIPs/switch-ins and positive redemptions/switch-outs/
dividends plus dated terminal current value. Dates use ACT/365. Decimal bisection
is bounded to 200 iterations and rates between -99.99% and 10000%. Same-day cashflows
are aggregated. Only a single negative-to-positive sign transition is solved;
nonconventional cashflows, incomplete history, transactions beyond valuation, missing
valuation, nonconvergence or mixed portfolio valuation dates return Unavailable.
No CAGR or simple return is presented as XIRR. Combined switching flows must contain
both matched sides for history to be verified complete.

Illustrative assumptions are domain values: Conservative 8%, Base 10%, Optimistic
12% p.a. Caller rates are validated to 0–30%. Monthly rate is nominal annual rate / 12;
end-of-month payments use recurrence V[m] = V[m-1]*(1+r/12) + payment[m]. A payment
is included only for ACTIVE instructions whose dates cover that future month.
Payment-day values are clamped to the final calendar day for eligibility. Projections
start next month; they do not guess whether this month's SIP executed. Calculations
use Decimal and round only at API serialization to two decimal places. Growth equals
projected value minus starting corpus minus future contributions. Year 0–10 is a
future illustration, not fabricated historical performance.

All current mutual-fund corpus compounds in the combined projection, including
schemes with no active SIP. Multiple active SIPs in one scheme receive a proportional
share of its corpus based on monthly amounts. Scheme actuals remain clearly labelled
and are not attributed to individual SIPs. Missing corpus is flagged; projections
use known values only, never historical contributions as a substitute. Individually
rounded displayed amounts may differ by a cent from combined amounts.

Family wealth composition should sum current settled stocks/ETFs, dated mutual-fund
holdings and relevant available cash. Never add delivery transactions again, MIS
turnover, or open-position notional. `family_composition` composes these separate
current-value components without changing brokerage arithmetic. Callers must provide
settled holdings and available cash from the existing brokerage views and show their
valuation times. It is an architecture boundary, not a claim of synchronized valuation.
Monthly reporting retains the original Zerodha CNC BUY amount and adds confirmed MF
PURCHASE/SIP contributions. Redemptions, switches and MIS are excluded.

Next required data: verified household member/account mapping; active/paused/stopped
SIP instructions, amounts, schedules and dates; authoritative scheme/plan/option/folio
identifiers and categories; complete dated transaction history with stable event IDs,
amounts, units and NAV where available; current dated holdings and verified remaining
cost basis; explicit history-completeness verification. A supported CAS adapter and
reviewed import workflow remain future work; the UI describes this honestly.

Projections are illustrations based on the selected annual return assumption, not
guaranteed returns. There is no trading capability.
