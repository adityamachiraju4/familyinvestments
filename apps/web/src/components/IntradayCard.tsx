import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Card, State } from "./UI";
import { dateLabel, money } from "../utils/format";
export function IntradayCard({ revision, enabled = true }: { revision: number; enabled?: boolean }) {
  const query = useQuery(api.intraday, revision, enabled);
  const rows = query.data?.positions || [];
  const total = (field: "realised_pnl" | "unrealised_pnl") =>
    query.data?.positions_available && rows.length > 0 && rows.every(row => row[field] !== null)
      ? rows.reduce((sum, row) => sum + Number(row[field]), 0) : null;
  return <Card title="Intraday Today">
    <p className="muted">MIS activity · Separate from delivery holdings and monthly investments</p>
    {!enabled ? <State empty="Connect Zerodha to view intraday positions." /> : query.loading || query.error
      ? <State loading={query.loading} error={query.error} /> : <>
        <p>{rows.length} symbols · {rows.reduce((sum, row) => sum + row.fill_count, 0)} recorded fills · {rows.filter(row => row.status === "OPEN").length} confirmed open MIS positions</p>
        <p>Realised P&amp;L {money(total("realised_pnl"))} · Open position P&amp;L {money(total("unrealised_pnl"))}</p>
        <p className="note">P&amp;L is provider-reported before charges. — means unavailable. Observed {dateLabel(query.data?.observed_at, true)}</p>
        {!query.data?.positions_available && <p className="note">Positions unavailable. Recorded fills are shown; current position status and P&amp;L are unconfirmed.</p>}
        {!rows.length && <p className="muted">No intraday activity available for today.</p>}
        {rows.map(row => <div className="plan-row" key={`${row.exchange}:${row.symbol}`}>
          <div><strong>{row.symbol}</strong><p className="muted">{row.exchange} · MIS · Intraday</p>
            <p>Bought {row.buy_quantity} · Sold {row.sell_quantity}</p>
            <p>{row.status === "CLOSED" ? "Closed position" : row.status === "OPEN" ? `Open position · Net ${row.open_quantity}` : row.source === "recorded_fills" ? `Position unconfirmed · Recorded net ${row.open_quantity ?? "—"}` : "Current position unavailable"}</p>
            <p>Buy turnover {money(row.buy_value)} · Sell turnover {money(row.sell_value)}</p>
          </div>
          <div><p>Realised P&amp;L {money(row.realised_pnl)}</p><p>Open position P&amp;L {money(row.unrealised_pnl)}</p></div>
        </div>)}
      </>}
  </Card>;
}
