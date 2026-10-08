# Delivery holdings and T1 valuation

Kite supplies settled `quantity` and unsettled `t1_quantity` separately. Both
are already validated and persisted in `holdings` (migration 0001). No schema
migration is required for this correction.

For delivery ownership, effective quantity is `quantity + t1_quantity`. Sync
uses it with provider Decimal average/last prices to calculate invested value,
market value and unrealised P&L, retaining existing rounding. The API exposes
both raw quantities plus effective quantity; Portfolio and holding detail show
effective ownership. Holding snapshots store effective quantity alongside the
corresponding values. Summary and allocation aggregate those corrected values.

Settlement updates the same account/exchange/symbol holding; moving units from
T1 to settled quantity does not change effective ownership. Contributions remain
based solely on recorded eligible CNC BUY fills, deduplicated by execution
identity. Holdings and settlement never create execution contributions. MIS
positions retain their separate intraday path.

A refresh recalculates current holdings and today's snapshot. Older historical
snapshots are not reconstructed because historical provider settlement data is
unavailable. Complete provider-list validation and transactional reconciliation
remain unchanged; invalid/failed fetches cannot deactivate current holdings.

Sources:
- https://kite.trade/docs/connect/v3/portfolio/
- https://kite.trade/forum/discussion/13001/t1-t2-and-realized-qty
