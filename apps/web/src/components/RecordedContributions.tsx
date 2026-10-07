import { api } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Card, State } from "./UI";
import { money, dateLabel, bucketLabels } from "../utils/format";
import type { Bucket } from "../api/types";
export function RecordedContributions({ revision }: { revision: number }) {
  const query = useQuery(api.contributions, revision);
  return (
    <Card title="Recorded purchases this month">
      {query.loading || query.error ? (
        <State loading={query.loading} error={query.error} />
      ) : query.data?.recorded_from ? (
        <>
          <div className="plan-total">
            {money(query.data.recorded_buy_amount)}
            <span>Executed delivery BUY fills · excludes charges</span>
          </div>
          {Object.entries(query.data.allocation)
            .filter(
              ([key, value]) =>
                ["NIFTY_50", "MID_CAP", "SMALL_CAP", "OTHER", "UNCLASSIFIED"].includes(key) ||
                Number(value) > 0,
            )
            .map(([bucket, value]) => (
              <div className="plan-row" key={bucket}>
                <span>{bucketLabels[bucket as Bucket]}</span>
                <strong>{money(value)} recorded</strong>
              </div>
            ))}
          {Number(query.data.allocation.UNCLASSIFIED) > 0 && (
            <p role="status" className="note">Some recorded investments are not yet classified into the monthly plan.</p>
          )}
          <p className="muted">
            Recorded history from {dateLabel(query.data.recorded_from)}.
          </p>
        </>
      ) : (
        <State empty="No recorded trade history yet." />
      )}
      <p className="note">
        Contribution tracking begins from recorded Zerodha trade history.
        Earlier purchases may be missing; this is not a complete monthly
        contribution total.
      </p>
    </Card>
  );
}
