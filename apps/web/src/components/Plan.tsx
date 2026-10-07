import type { Target, Summary, Bucket } from "../api/types";
import { bucketLabels, money, numeric } from "../utils/format";
import { Card } from "./UI";
const targets = (target: Target) => [
  { name: "Nifty 50", value: Number(target.nifty_target) },
  { name: "Midcap", value: Number(target.midcap_target) },
  { name: "Smallcap", value: Number(target.smallcap_target) },
];
export function Plan({ target }: { target: Target }) {
  return (
    <Card title="Monthly investment plan">
      <p className="muted">
        {new Intl.DateTimeFormat("en-IN", {
          month: "long",
          year: "numeric",
          timeZone: "Asia/Kolkata",
        }).format(new Date(target.month))}
      </p>
      <div className="plan-total">
        {money(target.total_target)}
        <span>Monthly target</span>
      </div>
      {targets(target).map((row) => (
        <div className="plan-row" key={row.name}>
          <span>{row.name}</span>
          <strong>
            {money(row.value)} <small>target</small>
          </strong>
        </div>
      ))}
      <p className="note">Purchase totals come from recorded delivery executions</p>
    </Card>
  );
}
export function Allocation({
  summary,
  target,
}: {
  summary?: Summary;
  target?: Target;
}) {
  const total = Object.values(summary?.allocation || {}).reduce<number>(
    (sum, v) => sum + (numeric(v) || 0),
    0,
  );
  return (
    <Card title="Portfolio allocation">
      <p className="muted">
        {summary
          ? "Active settled holdings · authoritative buckets"
          : "Monthly target allocation"}
      </p>
      {summary &&
        Object.entries(bucketLabels).map(([key, label]) => {
          const value = numeric(summary?.allocation[key as Bucket]);
          if (key === "UNCLASSIFIED" && value === 0) return null;
          const share = total > 0 ? ((value || 0) / total) * 100 : 0;
          return (
            <div className="allocation-row" key={key}>
              <div>
                <span>{label}</span>
                <span>
                  {money(value)} · {value === null
                    ? "—"
                    : total > 0
                      ? `${share.toFixed(2)}%`
                      : "—"}
                </span>
              </div>
              <div className="track">
                <span style={{ width: `${share}%` }} />
              </div>
            </div>
          );
        })}
      {summary && Number(summary.allocation.UNCLASSIFIED) > 0 && (
        <p className="note">Some holdings need classification. Their value remains included in your portfolio.</p>
      )}
      {summary && !total && <p className="muted">No allocation data yet.</p>}
      {target && (
        <>
          <p className="eyebrow target-heading">Target allocation</p>
          <div className="target-bar">
            {targets(target).map((r, i) => (
              <span
                key={r.name}
                style={{
                  flex: r.value,
                  background: ["#a6cbb6", "#758f80", "#485e52"][i],
                }}
              />
            ))}
          </div>
          <div className="target-legend">
            {targets(target).map((r) => (
              <span key={r.name}>
                {r.name}{" "}
                <strong>
                  {Number(target.total_target) > 0
                    ? ((r.value / Number(target.total_target)) * 100).toFixed(2)
                    : "—"}
                  %
                </strong>
              </span>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
