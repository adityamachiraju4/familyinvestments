import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { money, dateLabel } from "../utils/format";
export function Chart({
  data,
  label,
}: {
  data: { date: string; value: number }[];
  label: string;
}) {
  if (data.length < 2)
    return (
      <div className="chart-empty">
        <span className="chart-glyph">↗</span>
        <p>
          {data.length
            ? "Daily history will build as snapshots accumulate."
            : "Daily history will appear after portfolio snapshots are recorded."}
        </p>
      </div>
    );
  return (
    <div className="chart" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 15, right: 15, bottom: 0, left: 10 }}
        >
          <CartesianGrid stroke="#2c3330" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => dateLabel(v)}
            minTickGap={60}
            tick={{ fill: "#919d95", fontSize: 11 }}
          />
          <YAxis
            width={75}
            tickFormatter={(v) =>
              new Intl.NumberFormat("en-IN", { notation: "compact" }).format(v)
            }
            tick={{ fill: "#919d95", fontSize: 11 }}
          />
          <Tooltip
            labelFormatter={(v) => dateLabel(String(v))}
            formatter={(v) => [money(v), label]}
            contentStyle={{
              background: "#1b211e",
              border: "1px solid #39423c",
              borderRadius: 12,
            }}
          />
          <Line
            type="linear"
            dataKey="value"
            stroke="#a6cbb6"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
