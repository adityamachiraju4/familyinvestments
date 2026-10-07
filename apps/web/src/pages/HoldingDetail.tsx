import { useCallback } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Card, Metric, State } from "../components/UI";
import { Chart } from "../components/Chart";
import { bucketLabels, money, quantity, percent } from "../utils/format";
export default function HoldingDetail({ revision }: { revision: number }) {
  const { symbol = "" } = useParams();
  const [params] = useSearchParams();
  const exchange = params.get("exchange");
  const load = useCallback(() => api.history(symbol), [symbol]);
  const history = useQuery(load, revision),
    holdings = useQuery(api.holdings, revision);
  const current = holdings.data?.find(
    (h) => h.tradingsymbol === symbol && (!exchange || h.exchange === exchange),
  );
  const rows = (history.data || []).filter(
    (h) => !exchange || h.exchange === exchange,
  );
  const exchanges = [...new Set(rows.map((h) => h.exchange))];
  return (
    <>
      <Link className="back" to="/portfolio">
        ← Back to portfolio
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">HOLDING DETAIL</p>
          <h1>{symbol}</h1>
          <p className="muted">
            {current
              ? `${current.exchange} · ${bucketLabels[current.bucket]}`
              : "Current holding unavailable"}
          </p>
        </div>
      </div>
      {holdings.loading || holdings.error ? (
        <State loading={holdings.loading} error={holdings.error} />
      ) : current ? (
        <>
          <div className="metrics detail-metrics">
            <Metric label="Current value" value={current.current_value} />
            <Metric label="Invested value" value={current.invested_value} />
            <Metric
              label="Total P&L"
              value={current.unrealised_pnl}
              detail={percent(current.unrealised_pnl_percent)}
              pnl
            />
          </div>
          <Card>
            <div className="facts">
              <span>
                Quantity <strong>{quantity(current.quantity)}</strong>
              </span>
              <span>
                Average price <strong>{money(current.average_price)}</strong>
              </span>
              <span>
                Last price <strong>{money(current.last_price)}</strong>
              </span>
            </div>
          </Card>
        </>
      ) : (
        <State empty="No current holding found. Recorded history is shown below." />
      )}
      <Card title="Market value over time">
        {history.loading || history.error ? (
          <State loading={history.loading} error={history.error} />
        ) : exchanges.length > 1 ? (
          <State empty="Select this holding from Portfolio to view history for a specific exchange." />
        ) : (
          <Chart
            label="Holding market value"
            data={rows.map((h) => ({
              date: h.snapshot_date,
              value: Number(h.market_value),
            }))}
          />
        )}
      </Card>
    </>
  );
}
