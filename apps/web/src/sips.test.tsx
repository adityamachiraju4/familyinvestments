import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SIPPlanning } from "./components/SIPPlanning";
import { investments } from "./api/investments";
vi.mock("./api/investments", () => ({
  investments: { sips: vi.fn(), summary: vi.fn(), projections: vi.fn() },
}));
vi.mock("recharts", () => ({
  ResponsiveContainer: () => <div>Projection chart</div>,
  LineChart: () => null,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  CartesianGrid: () => null,
}));
const point = {
  future_contributions: "12000",
  projected_growth: "565.56",
  projected_value: "12565.56",
  total_contributions: "12000",
};
beforeEach(() => {
  vi.mocked(investments.sips).mockResolvedValue([]);
  vi.mocked(investments.summary).mockResolvedValue({
    active_sips: 0,
    monthly_sip: "0",
    contributed: "0",
    current_value: "0",
    gain_loss: null,
    xirr: null,
    valuation_date: null,
    history_complete: false,
    monthly_mf_contributions: "0",
  });
  vi.mocked(investments.projections).mockResolvedValue({
    scenarios: [
      { name: "Conservative", annual_return: "8" },
      { name: "Base", annual_return: "10" },
      { name: "Optimistic", annual_return: "12" },
    ],
    assumption_percent: "10",
    disclosure:
      "Projections are illustrations based on the selected annual return assumption, not guaranteed returns.",
    corpus_complete: true,
    starting_corpus: "0",
    monthly_sip: "1000",
    sips: [],
    combined: { one_year: point, five_years: point, ten_years: point },
    chart: [],
  });
});
it("shows honest empty state, horizons, combined card and disclosure with no trading controls", async () => {
  render(<SIPPlanning revision={0} />);
  expect(await screen.findByText("No SIPs imported yet.")).toBeInTheDocument();
  expect(
    await screen.findByText("At your current SIP pace"),
  ).toBeInTheDocument();
  for (const label of ["1Y", "5Y", "10Y"])
    expect(screen.getByText(label)).toBeInTheDocument();
  expect(screen.getByText(/Projections are illustrations/)).toBeVisible();
  expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  expect(
    screen.queryByRole("button", { name: /buy|sell|trade|redeem/i }),
  ).toBeNull();
});
it("selects configured scenario and reloads projections", async () => {
  render(<SIPPlanning revision={0} />);
  const selector = await screen.findByRole("combobox");
  fireEvent.change(selector, { target: { value: "8" } });
  await waitFor(() =>
    expect(investments.projections).toHaveBeenCalledWith("8"),
  );
});
it("renders per SIP scheme actuals and projections", async () => {
  vi.mocked(investments.sips).mockResolvedValue([
    {
      id: 1,
      scheme_name: "Fixture scheme",
      source: "CAS",
      category: "UNCLASSIFIED",
      monthly_amount: "1000",
      sip_day: 7,
      start_date: "2025-01-01",
      status: "ACTIVE",
      scheme_actual: {
        contributed: "1000",
        current_value: "1100",
        gain_loss: "100",
        xirr: "10",
        valuation_date: "2026-01-01",
        history_complete: true,
      },
    },
  ]);
  const p = await investments.projections();
  vi.mocked(investments.projections).mockResolvedValue({
    ...p,
    sips: [
      {
        id: 1,
        scheme_name: "Fixture scheme",
        allocated_starting_corpus: "1100",
        projections: p.combined,
      },
    ],
  });
  render(<SIPPlanning revision={0} />);
  await waitFor(() =>
    expect(screen.getAllByText("Fixture scheme")).toHaveLength(2),
  );
  expect(screen.getByText(/Scheme XIRR/)).toHaveTextContent("10%");
});
