import { useState } from "react";
import { api } from "../api/client";
import type { Snapshot } from "../api/types";
import { useQuery } from "../hooks/useQuery";
import { Card, State, Pnl } from "../components/UI";
import { Chart } from "../components/Chart";
import { money, dateLabel } from "../utils/format";
const load = () => api.snapshots(3650);
const metrics = {
  holdings_market_value: "Portfolio value",
  holdings_invested_value: "Invested capital",
  available_cash: "Cash balance",
  total_pnl: "Total P&L",
  total_account_value: "Holdings + cash",
};
export default function History({ revision }: { revision: number }) {
  const query = useQuery(load, revision);
  const [metric, setMetric] = useState<keyof typeof metrics>(
    "total_account_value",
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">THE LONG VIEW</p>
          <h1>History</h1>
          <p className="muted">Daily snapshots of your portfolio.</p>
        </div>
      </div>
      <Card>
        <div className="card-heading">
          <h2>Portfolio over time</h2>
          <label className="select-label">
            Metric{" "}
            <select
              value={metric}
              onChange={(e) =>
                setMetric(e.target.value as keyof typeof metrics)
              }
            >
              {Object.entries(metrics).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        </div>
        {query.loading || query.error ? (
          <State loading={query.loading} error={query.error} />
        ) : (
          <Chart
            label={metrics[metric]}
            data={(query.data || []).map((s) => ({
              date: s.snapshot_date,
              value: Number(s[metric as keyof Snapshot]),
            }))}
          />
        )}
      </Card>
      <Card title="Historical snapshots">
        {query.loading || query.error || !query.data?.length ? (
          <State
            loading={query.loading}
            error={query.error}
            empty="Daily history will appear after portfolio snapshots are recorded."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Date",
                    "Portfolio value",
                    "Invested value",
                    "Cash",
                    "Holdings + cash",
                    "P&L / %",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...query.data].reverse().map((s) => (
                  <tr key={s.snapshot_date}>
                    <td>{dateLabel(s.snapshot_date)}</td>
                    <td>{money(s.holdings_market_value)}</td>
                    <td>{money(s.holdings_invested_value)}</td>
                    <td>{money(s.available_cash)}</td>
                    <td>{money(s.total_account_value)}</td>
                    <td>
                      <Pnl value={s.total_pnl} rate={s.total_pnl_percent} />
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
