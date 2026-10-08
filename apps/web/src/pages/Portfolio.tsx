import { useState } from "react";
import { Link } from "react-router-dom";
import { ActivityCard } from "../components/ActivityCard";
import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Card, Pnl, State } from "../components/UI";
import { money, quantity, dateLabel, bucketLabels } from "../utils/format";
export default function Portfolio({ revision }: { revision: number }) {
  const query = useQuery(api.holdings, revision);
  const [ascending, setAscending] = useState(true);
  const rows = [...(query.data || [])].sort((a, b) =>
    ascending
      ? a.tradingsymbol.localeCompare(b.tradingsymbol)
      : b.tradingsymbol.localeCompare(a.tradingsymbol),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR ASSETS</p>
          <h1>Portfolio</h1>
          <p className="muted">A clear view of every holding.</p>
        </div>
      </div>
      <ActivityCard revision={revision} awaitingOnly />
      <Card>
        {query.loading || query.error || !rows.length ? (
          <State
            loading={query.loading}
            error={query.error}
            empty="No holdings synced yet."
          />
        ) : (
          <div className="table-scroll">
            <button
              className="mobile-sort"
              onClick={() => setAscending(!ascending)}
            >
              Sort symbol {ascending ? "↑" : "↓"}
            </button>
            <table className="holdings">
              <thead>
                <tr>
                  <th>
                    <button onClick={() => setAscending(!ascending)}>
                      Symbol {ascending ? "↑" : "↓"}
                    </button>
                  </th>
                  {[
                    "Exchange",
                    "Bucket",
                    "Quantity",
                    "Average price",
                    "Last price",
                    "Invested value",
                    "Current value",
                    "P&L / %",
                    "Last synced",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((h) => (
                  <tr key={`${h.exchange}:${h.tradingsymbol}`}>
                    <td data-label="Symbol">
                      <Link
                        className="symbol"
                        to={`/portfolio/${encodeURIComponent(h.tradingsymbol)}?exchange=${encodeURIComponent(h.exchange)}`}
                      >
                        {h.tradingsymbol} ↗
                      </Link>
                    </td>
                    <td data-label="Exchange">{h.exchange}</td>
                    <td data-label="Bucket">{bucketLabels[h.bucket]}</td>
                    <td data-label="Quantity">{quantity(h.effective_quantity ?? h.quantity + (h.t1_quantity ?? 0))}</td>
                    <td data-label="Average price">{money(h.average_price)}</td>
                    <td data-label="Last price">{money(h.last_price)}</td>
                    <td data-label="Invested value">
                      {money(h.invested_value)}
                    </td>
                    <td data-label="Current value">{money(h.current_value)}</td>
                    <td data-label="P&L / %">
                      <Pnl
                        value={h.unrealised_pnl}
                        rate={h.unrealised_pnl_percent}
                      />
                    </td>
                    <td data-label="Last synced">
                      {dateLabel(h.synced_at, true)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
