import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Card, State } from "./UI";
import { money, quantity, dateLabel, bucketLabels } from "../utils/format";
import type { Execution } from "../api/types";
function ExecutionRow({ row }: { row: Execution }) {
  return (
    <article className="execution-row">
      <div>
        <strong>{row.symbol}</strong>
        <span className="activity-badge">{row.transaction_type}</span>
        <p className="muted">
          {row.exchange} · {row.product} · {bucketLabels[row.bucket]} ·{" "}
          {dateLabel(row.executed_at, true)}
        </p>
      </div>
      <div className="execution-amount">
        <strong>{money(row.amount)}</strong>
        <p className="muted">
          {quantity(row.quantity)} units at {money(row.average_price)}
        </p>
      </div>
      <div className="execution-status">
        <span>
          Executed · {row.fill_count} {row.fill_count === 1 ? "fill" : "fills"}
        </span>
        <small>
          {row.holding_status === "AWAITING_HOLDINGS"
            ? "Awaiting holdings update"
            : row.holding_status === "HOLDING_PRESENT_UNCONFIRMED"
              ? "Holding exists; today’s quantity not confirmed"
              : row.holding_status === "NETTED_BY_SELLS"
                ? "Offset by today’s delivery sells"
                : "Recorded execution"}
        </small>
      </div>
    </article>
  );
}
export function ActivityCard({
  revision,
  awaitingOnly = false,
}: {
  revision: number;
  awaitingOnly?: boolean;
}) {
  const query = useQuery(api.activity, revision);
  const rows = awaitingOnly
    ? query.data?.awaiting_holdings
    : query.data?.executed;
  if (awaitingOnly && !query.loading && !query.error && !rows?.length)
    return null;
  return (
    <Card
      title={awaitingOnly ? "Awaiting holdings update" : "Today’s Activity"}
    >
      {query.loading || query.error ? (
        <State loading={query.loading} error={query.error} />
      ) : (
        <>
          {!query.data?.last_synced_at && (
            <p className="note">
              Activity has not been refreshed for today. Connect Zerodha and
              Refresh to check executions.
            </p>
          )}
          {!awaitingOnly && query.data && (
            <div className="activity-summary">
              <span>
                <strong>{query.data.executed.length}</strong> Executed orders
              </span>
              <span>
                <strong>{query.data.open_pending_count}</strong> Open / pending
              </span>
              <span>
                <strong>{query.data.rejected_cancelled_count}</strong> Rejected
                / cancelled
              </span>
            </div>
          )}
          {rows?.length ? (
            rows.map((row) => (
              <ExecutionRow
                key={`${row.order_id}:${row.exchange}:${row.transaction_type}:${row.product}`}
                row={row}
              />
            ))
          ) : (
            <State
              empty={
                query.data?.last_synced_at
                  ? "No executions recorded today."
                  : "No execution data recorded yet."
              }
            />
          )}
          <p className="muted">
            Executions are activity. Their amounts are not added to holdings and
            cash totals. Charges are unavailable.
          </p>
          {!awaitingOnly && !!query.data?.orders.length && (
            <details className="order-context">
              <summary>Today’s orders · {query.data.orders.length}</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {[
                        "Symbol",
                        "Side / product",
                        "Requested",
                        "Filled",
                        "Status",
                        "Placed",
                      ].map((label) => (
                        <th key={label}>{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.orders.map((row) => (
                      <tr key={row.order_id}>
                        <td>
                          {row.symbol} <small>{row.exchange}</small>
                        </td>
                        <td>
                          {row.transaction_type} · {row.product}
                        </td>
                        <td>{quantity(row.quantity)}</td>
                        <td>{quantity(row.filled_quantity)}</td>
                        <td>{row.status}</td>
                        <td>{dateLabel(row.timestamp, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </Card>
  );
}
