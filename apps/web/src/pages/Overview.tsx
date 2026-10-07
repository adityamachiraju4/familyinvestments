import { useState, useCallback } from "react";
import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Card, Metric, State } from "../components/UI";
import { Chart } from "../components/Chart";
import { Allocation, Plan } from "../components/Plan";
import { IntradayCard } from "../components/IntradayCard";
import { ActivityCard } from "../components/ActivityCard";
import { money, percent } from "../utils/format";
export default function Overview({
  revision,
  canFetchSummary = true,
}: {
  revision: number;
  canFetchSummary?: boolean;
}) {
  const summary = useQuery(api.summary, revision, canFetchSummary),
    target = useQuery(api.target, revision);
  const [range, setRange] = useState("30D");
  const load = useCallback(
    () =>
      api.snapshots(
        range === "ALL" ? 3650 : range === "1Y" ? 365 : parseInt(range),
      ),
    [range],
  );
  const history = useQuery(load, revision);
  const days = range === "ALL" ? null : range === "1Y" ? 365 : parseInt(range);
  const today = new Date().toLocaleDateString("en-CA", {
    timeZone: "Asia/Kolkata",
  });
  const cutoff =
    days === null ? null : new Date(today).getTime() - (days - 1) * 86400000;
  const visibleHistory = (history.data || []).filter(
    (s) => cutoff === null || new Date(s.snapshot_date).getTime() >= cutoff,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR HOUSEHOLD, AT A GLANCE</p>
          <h1>Overview</h1>
        </div>
        <span className="badge">Read-only portfolio</span>
      </div>
      {!canFetchSummary ? (
        <State empty="Connect Zerodha to update holdings and cash." />
      ) : summary.loading || summary.error ? (
        <State loading={summary.loading} error={summary.error} />
      ) : (
        <>
          <section className="hero">
            <p className="eyebrow">HOLDINGS + CASH</p>
            <div className="hero-value">
              {money(summary.data?.total_account_value)}
            </div>
            <p className="muted">
              Holdings and available cash · {summary.data?.holding_count}{" "}
              holdings. Executions awaiting holdings are shown separately.
            </p>
          </section>
          <div className="metrics">
            <Metric
              label="Portfolio value"
              value={summary.data?.holdings_market_value}
            />
            <Metric
              label="Available cash"
              value={summary.data?.available_cash}
            />
            <Metric
              label="Invested"
              value={summary.data?.holdings_invested_value}
            />
            <Metric
              label="Overall P&L"
              value={summary.data?.total_pnl}
              detail={percent(summary.data?.total_pnl_percent)}
              pnl
            />
            <Metric
              label="Today's P&L"
              value={null}
              detail="Not available from current data source"
            />
          </div>
        </>
      )}
      <Card>
        <div className="card-heading">
          <div>
            <h2>Portfolio growth</h2>
            <p className="muted">Holdings and cash over time</p>
          </div>
          <div className="tabs" aria-label="History range">
            {["7D", "30D", "90D", "1Y", "ALL"].map((r) => (
              <button
                key={r}
                aria-pressed={r === range}
                onClick={() => setRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
        {history.loading || history.error ? (
          <State loading={history.loading} error={history.error} />
        ) : (
          <Chart
            label="Holdings + cash"
            data={visibleHistory.map((s) => ({
              date: s.snapshot_date,
              value: Number(s.total_account_value),
            }))}
          />
        )}
      </Card>
      <IntradayCard revision={revision} enabled={canFetchSummary} />
      <ActivityCard revision={revision} />
      <div className="two-column">
        {canFetchSummary && summary.data ? (
          <Allocation summary={summary.data} target={target.data} />
        ) : (
          <Card title="Portfolio allocation">
            <State loading={summary.loading} error={summary.error} />
          </Card>
        )}
        {target.data ? (
          <Plan target={target.data} />
        ) : (
          <Card title="Monthly investment plan">
            <State loading={target.loading} error={target.error} />
          </Card>
        )}
      </div>
    </>
  );
}
