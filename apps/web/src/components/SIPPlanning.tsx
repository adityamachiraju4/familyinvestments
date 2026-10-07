import { useCallback, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { investments, type Horizons } from "../api/investments";
import { useQuery } from "../hooks/useQuery";
import { Card, State } from "./UI";
import { money, dateLabel } from "../utils/format";
const horizons = [
  ["one_year", "1Y"],
  ["five_years", "5Y"],
  ["ten_years", "10Y"],
] as const;
const value = (amount: string | null) =>
  amount === null ? "Unavailable" : money(amount);
function HorizonRows({
  points,
  combined = false,
}: {
  points: Horizons;
  combined?: boolean;
}) {
  return (
    <div className="sip-horizons">
      {horizons.map(([key, label]) => (
        <div key={key}>
          <h3>{label}</h3>
          <p>
            Future contributions{" "}
            <strong>{money(points[key].future_contributions)}</strong>
          </p>
          {combined && (
            <p>
              Total recorded + future contributions{" "}
              <strong>{money(points[key].total_contributions)}</strong>
            </p>
          )}
          <p>
            Estimated growth{" "}
            <strong>{money(points[key].projected_growth)}</strong>
          </p>
          <p>
            Projected corpus{" "}
            <strong>{money(points[key].projected_value)}</strong>
          </p>
        </div>
      ))}
    </div>
  );
}
export function SIPPlanning({ revision }: { revision: number }) {
  const [rate, setRate] = useState("10");
  const load = useCallback(() => investments.projections(rate), [rate]);
  const sips = useQuery(investments.sips, revision);
  const summary = useQuery(investments.summary, revision);
  const projection = useQuery(load, revision);
  return (
    <>
      <Card title="SIP overview">
        {summary.loading || summary.error ? (
          <State loading={summary.loading} error={summary.error} />
        ) : (
          summary.data && (
            <>
              <div className="sip-horizons">
                <p>
                  Active SIPs <strong>{summary.data.active_sips}</strong>
                </p>
                <p>
                  Monthly SIP total{" "}
                  <strong>{money(summary.data.monthly_sip)}</strong>
                </p>
                <p>
                  Recorded contributed{" "}
                  <strong>{money(summary.data.contributed)}</strong>
                </p>
                <p>
                  Current mutual-fund value{" "}
                  <strong>{value(summary.data.current_value)}</strong>
                </p>
                <p>
                  Gain/loss <strong>{value(summary.data.gain_loss)}</strong>
                </p>
                <p>
                  XIRR{" "}
                  <strong>
                    {summary.data.xirr === null
                      ? "Unavailable"
                      : `${summary.data.xirr}%`}
                  </strong>
                </p>
              </div>
              <p className="note">
                Actual values come from imported valuations. Recorded
                contributions may be incomplete.
              </p>
            </>
          )
        )}
      </Card>
      <Card title="Your SIPs">
        {sips.loading || sips.error ? (
          <State loading={sips.loading} error={sips.error} />
        ) : !sips.data?.length ? (
          <>
            <State empty="No SIPs imported yet." />
            <p className="muted">
              A future verified CAS or supported statement import will add your
              SIPs, transactions and current valuations.
            </p>
          </>
        ) : (
          sips.data.map((sip) => (
            <article key={sip.id} className="sip-row">
              <h3>{sip.scheme_name}</h3>
              <p>
                {sip.source} · {sip.category} · {sip.status}
              </p>
              <p>
                {money(sip.monthly_amount)}/month · SIP day{" "}
                {sip.sip_day ?? "Unavailable"} · Started{" "}
                {dateLabel(sip.start_date)}
              </p>
              <p>
                Scheme contributed {money(sip.scheme_actual.contributed)} ·
                Scheme current value {value(sip.scheme_actual.current_value)} ·
                Scheme XIRR{" "}
                {sip.scheme_actual.xirr === null
                  ? "Unavailable"
                  : `${sip.scheme_actual.xirr}%`}
              </p>
              <p className="note">
                Actuals are per scheme/folio, shared by any SIPs in that scheme.
                Valuation:{" "}
                {sip.scheme_actual.valuation_date
                  ? dateLabel(sip.scheme_actual.valuation_date)
                  : "Unavailable"}
              </p>
            </article>
          ))
        )}
      </Card>
      <Card title="Future value">
        <p className="note">
          Projections are illustrations based on the selected annual return
          assumption, not guaranteed returns.
        </p>
        {projection.loading || projection.error ? (
          <State loading={projection.loading} error={projection.error} />
        ) : (
          projection.data && (
            <>
              <label>
                Illustrative return assumption{" "}
                <select
                  value={rate}
                  onChange={(event) => setRate(event.target.value)}
                >
                  {projection.data.scenarios.map((s) => (
                    <option
                      key={s.name}
                      value={String(Number(s.annual_return))}
                    >
                      {s.name} {Number(s.annual_return)}% p.a.
                    </option>
                  ))}
                </select>
              </label>
              <p className="muted">
                Monthly compounding; contributions at month end. Projections
                begin with recorded current valuations.
              </p>
              {!projection.data.corpus_complete && (
                <p role="status" className="note">
                  Current valuations are missing for some schemes. These
                  illustrations use only the known corpus.
                </p>
              )}
              {projection.data.sips.map((sip) => (
                <article key={sip.id}>
                  <h3>{sip.scheme_name}</h3>
                  <p className="note">
                    Allocated starting corpus{" "}
                    {money(sip.allocated_starting_corpus)}. Multiple active SIPs
                    share a scheme corpus in proportion to monthly amounts.
                  </p>
                  <HorizonRows points={sip.projections} />
                </article>
              ))}
            </>
          )
        )}
      </Card>
      {projection.data && !projection.loading && !projection.error && (
        <>
          <Card title="At your current SIP pace">
            <p className="plan-total">
              Monthly SIP: {money(projection.data.monthly_sip)}
            </p>
            <p className="note">
              Includes all recorded mutual-fund corpus, including schemes with
              paused or stopped SIPs.
            </p>
            <HorizonRows points={projection.data.combined} combined />
          </Card>
          <Card title="Illustrative portfolio projection · Year 0 → Year 10">
            <div
              className="chart"
              role="img"
              aria-label="Total contributed and projected portfolio value over ten years"
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={projection.data.chart.map((p) => ({
                    year: p.year,
                    contributed: Number(p.total_contributions),
                    corpus: Number(p.projected_value),
                  }))}
                >
                  <CartesianGrid stroke="#2c3330" />
                  <XAxis dataKey="year" />
                  <YAxis
                    tickFormatter={(v) =>
                      new Intl.NumberFormat("en-IN", {
                        notation: "compact",
                      }).format(v)
                    }
                  />
                  <Tooltip formatter={(v) => money(v)} />
                  <Legend />
                  <Line
                    dataKey="contributed"
                    name="Total recorded + future contributions"
                    stroke="#919d95"
                    dot={false}
                  />
                  <Line
                    dataKey="corpus"
                    name="Projected portfolio value"
                    stroke="#a6cbb6"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="note">
              Illustrative future values; recorded contributions are not a
              reconstructed performance history.
            </p>
          </Card>
        </>
      )}
    </>
  );
}
