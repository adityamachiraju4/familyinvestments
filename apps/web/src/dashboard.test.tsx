import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { money, percent, quantity, pnlClass } from "./utils/format";
import { request, refreshPortfolio } from "./api/client";
import Overview from "./pages/Overview";
import Portfolio from "./pages/Portfolio";
import HoldingDetail from "./pages/HoldingDetail";
import App from "./App";
import { ActivityCard } from "./components/ActivityCard";
import { RecordedContributions } from "./components/RecordedContributions";
const summary = {
  holdings_market_value: "120",
  holdings_invested_value: "100",
  available_cash: "30",
  total_account_value: "150",
  total_pnl: "20",
  total_pnl_percent: "20",
  holding_count: 1,
  allocation: { OTHER: "120" },
  last_sync_at: null,
};
function mockApi(connected = true, stale = false) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    const data = path.endsWith("/auth/session")
      ? { authenticated: true, csrf_token: "test-csrf", expires_at: null }
      : path.endsWith("/summary")
      ? summary
      : path.endsWith("/status")
        ? {
            connection_status: connected ? "connected" : "disconnected",
            last_sync_at: null,
            token_valid: connected,
            refresh_required: stale,
            last_refresh_at: null,
          }
        : path.includes("monthly-target")
          ? {
              month: "2026-10-01",
              total_target: "300",
              nifty_target: "160",
              midcap_target: "100",
              smallcap_target: "40",
            }
          : path.includes("/activity/today")
            ? {
                date: "2026-10-07",
                last_synced_at: null,
                executed: [],
                orders: [],
                awaiting_holdings: [],
                open_pending_count: 0,
                rejected_cancelled_count: 0,
              }
            : path.includes("/portfolio/refresh")
              ? {
                  status: "ok",
                  holdings_synced: 1,
                  orders_synced: 0,
                  trades_synced: 0,
                  last_refresh_at: null,
                }
              : [];
    return new Response(JSON.stringify(data), { status: 200 });
  });
}
describe("formatting", () => {
  it("formats Indian money and missing values", () => {
    expect(money("14019.89")).toBe("₹14,019.89");
    expect(money(null)).toBe("—");
    expect(money("bad")).toBe("—");
    expect(percent("17.598")).toBe("+17.60%");
    expect(quantity(10)).toBe("10");
  });
  it("uses positive negative and neutral colors", () => {
    expect(pnlClass(1)).toBe("positive");
    expect(pnlClass(-1)).toBe("negative");
    expect(pnlClass(0)).toBe("neutral");
  });
});
it("handles JSON decimal responses", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response('{"value":"12.30"}'),
  );
  expect(await request("/test")).toEqual({ value: "12.30" });
});
it("does not expose provider errors", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("secret", { status: 500 }),
  );
  await expect(request("/test")).rejects.toThrow(
    "Unable to load portfolio data",
  );
});
it("renders core API values and unavailable day P&L", async () => {
  mockApi();
  render(<Overview revision={0} />);
  expect(await screen.findByText("₹150.00")).toBeInTheDocument();
  expect(screen.getByText("₹120.00")).toBeInTheDocument();
  expect(
    screen.getByText("Not available from current data source"),
  ).toBeInTheDocument();
  expect(screen.getByText("—", { selector: ".metric" })).toBeInTheDocument();
});
it("renders no holdings state", async () => {
  mockApi();
  render(
    <MemoryRouter>
      <Portfolio revision={0} />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText("No holdings synced yet."),
  ).toBeInTheDocument();
});
it("shows disconnected status", async () => {
  mockApi(false);
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  expect(
    await screen.findByRole("button", { name: "Connect Zerodha for today" }),
  ).toBeInTheDocument();
});
it("calls the canonical refresh endpoint", async () => {
  const fetch = mockApi();
  await refreshPortfolio();
  expect(String(fetch.mock.calls[0][0])).toContain("/portfolio/refresh");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][1]?.method).toBe("POST");
});
it("refresh button refetches after completing mutations", async () => {
  const fetch = mockApi();
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByText("₹150.00");
  fetch.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "↻ Refresh" }));
  await screen.findByText("Portfolio refreshed successfully.");
  await waitFor(() =>
    expect(
      fetch.mock.calls.some((c) => String(c[0]).endsWith("/summary")),
    ).toBe(true),
  );
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("/portfolio/refresh")),
  ).toHaveLength(1);
});

it("stops refresh before snapshot when sync fails", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify({ error: "credentials_invalid" }), { status: 401 }));
  await expect(refreshPortfolio()).rejects.toThrow(
    "Zerodha connection expired",
  );
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("replaces stale connected status when the session is rejected", async () => {
  mockApi();
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByText("Zerodha Connected");
  fireEvent(window, new Event("zerodha-session-expired"));
  expect(
    await screen.findByRole("button", { name: "Connect Zerodha for today" }),
  ).toBeInTheDocument();
});

it("auto-refreshes stale connected data only once", async () => {
  const fetch = mockApi(true, true);
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByText("Portfolio refreshed successfully.");
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter((c) =>
        String(c[0]).includes("/portfolio/refresh"),
      ),
    ).toHaveLength(1),
  );
  fireEvent.click(screen.getByRole("link", { name: /History/ }));
  await screen.findByRole("heading", { name: "History" });
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).includes("/portfolio/refresh")),
  ).toHaveLength(1);
});
it("does not automatically refresh an expired session", async () => {
  const fetch = mockApi(false, true);
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "Connect Zerodha for today" });
  expect(
    fetch.mock.calls.some((c) => String(c[0]).includes("/portfolio/refresh")),
  ).toBe(false);
  expect(fetch.mock.calls.some((c) => String(c[0]).endsWith("/summary"))).toBe(
    false,
  );
});
it("prevents concurrent manual refresh clicks", async () => {
  const fetch = mockApi();
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByText("₹150.00");
  let finish: (value: Response) => void = () => {};
  const original = fetch.getMockImplementation()!;
  fetch.mockImplementation((input, init) =>
    String(input).endsWith("/portfolio/refresh")
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : original(input, init),
  );
  const button = screen.getByRole("button", { name: "↻ Refresh" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("/portfolio/refresh")),
  ).toHaveLength(1);
  finish(new Response(JSON.stringify({ status: "ok" })));
  await screen.findByText("Portfolio refreshed successfully.");
});
it("normalizes reconnect-required refresh results", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "reconnect_required" })),
  );
  await expect(refreshPortfolio()).rejects.toThrow(
    "Zerodha connection expired",
  );
});

it("shows executed fills separately with awaiting holdings and null charges", async () => {
  const execution = {
    symbol: "NIFTYBEES",
    exchange: "NSE",
    transaction_type: "BUY",
    product: "CNC",
    quantity: 2,
    average_price: "281",
    amount: "562",
    bucket: "NIFTY_50",
    executed_at: "2026-10-07T09:15:00+05:30",
    order_id: "o1",
    fill_count: 2,
    charges: null,
    holding_status: "AWAITING_HOLDINGS",
  };
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        date: "2026-10-07",
        last_synced_at: "2026-10-07T09:20:00+05:30",
        executed: [execution],
        awaiting_holdings: [execution],
        orders: [],
        open_pending_count: 0,
        rejected_cancelled_count: 0,
      }),
    ),
  );
  render(<ActivityCard revision={0} />);
  expect(await screen.findByText("NIFTYBEES")).toBeInTheDocument();
  expect(screen.getByText("Awaiting holdings update")).toBeInTheDocument();
  expect(screen.getByText("2 units at ₹281.00")).toBeInTheDocument();
  expect(screen.getByText(/Charges are unavailable/)).toBeInTheDocument();
});
it("labels recorded contributions as incomplete monthly coverage", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        month: "2026-10-01",
        recorded_from: "2026-10-07",
        recorded_buy_amount: "562",
        allocation: {
          NIFTY_50: "562",
          MID_CAP: "0",
          SMALL_CAP: "0",
          LARGE_CAP: "0",
          OTHER: "0",
        },
        history_complete: false,
        charges: null,
      }),
    ),
  );
  render(<RecordedContributions revision={0} />);
  expect(await screen.findByText("₹562.00")).toBeInTheDocument();
  expect(
    screen.getByText(/not a complete monthly contribution total/),
  ).toBeInTheDocument();
});

it("keeps unclassified purchases visible with a classification warning", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    month: "2026-10-01", recorded_from: "2026-10-07", recorded_buy_amount: "540.36",
    allocation: { NIFTY_50: "0", MID_CAP: "0", SMALL_CAP: "0", LARGE_CAP: "0", OTHER: "0", UNCLASSIFIED: "540.36" },
    history_complete: false, charges: null,
  })));
  render(<RecordedContributions revision={0} />);
  expect(await screen.findByText("Needs classification")).toBeInTheDocument();
  expect(screen.getByText("₹540.36 recorded")).toBeInTheDocument();
  expect(screen.getByText(/Some recorded investments are not yet classified/)).toBeInTheDocument();
});

it("shows unknown executed investments without assigning them to Other", async () => {
  const execution = {
    symbol: "NEWETF", exchange: "NSE", transaction_type: "BUY", product: "CNC",
    quantity: 3, average_price: "180.12", amount: "540.36", bucket: "UNCLASSIFIED",
    executed_at: "2026-10-07T09:15:00+05:30", order_id: "new", fill_count: 1,
    charges: null, holding_status: "AWAITING_HOLDINGS",
  };
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    date: "2026-10-07", last_synced_at: null, executed: [execution], awaiting_holdings: [execution],
    orders: [], open_pending_count: 0, rejected_cancelled_count: 0,
  })));
  render(<ActivityCard revision={0} />);
  expect(await screen.findByText("NEWETF")).toBeInTheDocument();
  expect(screen.getByText(/Needs classification/)).toBeInTheDocument();
  expect(screen.getByText("3 units at ₹180.12")).toBeInTheDocument();
  expect(screen.getByText("₹540.36")).toBeInTheDocument();
});

it("handles successful callback, removes marker, refreshes status and portfolio once", async () => {
  const fetch = mockApi(true, false);
  const { BrowserRouter } = await import("react-router-dom");
  window.history.replaceState({}, "", "/?zerodha=connected&keep=yes#test");
  render(<BrowserRouter><App /></BrowserRouter>);
  expect(await screen.findByText("Zerodha connected successfully.")).toBeInTheDocument();
  await screen.findByText("Portfolio refreshed successfully.");
  expect(window.location.search).toBe("?keep=yes");
  expect(window.location.hash).toBe("#test");
  expect(fetch.mock.calls.filter(([url]) => String(url).includes("/portfolio/refresh"))).toHaveLength(1);
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/status")).length).toBeGreaterThanOrEqual(2));
  window.history.replaceState({}, "", "/");
});
it("handles failure callback with safe reconnect message and removes marker", async () => {
  const fetch = mockApi(false);
  const { BrowserRouter } = await import("react-router-dom");
  window.history.replaceState({}, "", "/?zerodha=connect_failed");
  render(<BrowserRouter><App /></BrowserRouter>);
  expect(await screen.findByText("Zerodha connection could not be completed. Please try again.")).toBeInTheDocument();
  expect(window.location.search).toBe("");
  expect(await screen.findByRole("button", { name: "Connect Zerodha for today" })).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([url]) => String(url).includes("/portfolio/refresh"))).toHaveLength(0);
});

it("shows separate intraday positions and unavailable P&L without trading controls", async () => {
  const { IntradayCard } = await import("./components/IntradayCard");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    date: "2026-10-07", observed_at: null, positions_available: false,
    positions: [{ symbol: "NYKAA", exchange: "NSE", product: "MIS", activity_type: "INTRADAY",
      buy_quantity: 5, sell_quantity: 3, open_quantity: 2, buy_value: "500", sell_value: "330",
      realised_pnl: null, unrealised_pnl: null, status: "UNCONFIRMED", source: "recorded_fills", fill_count: 2 }]
  })));
  render(<IntradayCard revision={0} />);
  expect(await screen.findByText("NYKAA")).toBeInTheDocument();
  expect(screen.getByText("Intraday Today")).toBeInTheDocument();
  expect(screen.getByText("Bought 5 · Sold 3")).toBeInTheDocument();
  expect(screen.getByText("Position unconfirmed · Recorded net 2")).toBeInTheDocument();
  expect(screen.getAllByText(/Realised P&L —/).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("portfolio allocation shows unclassified amount separately from target allocation", async () => {
  const { Allocation } = await import("./components/Plan");
  render(<Allocation summary={{ ...summary, allocation: { NIFTY_50: "0", MID_CAP: "0", SMALL_CAP: "0", LARGE_CAP: "0", OTHER: "0", UNCLASSIFIED: "8897.41" } }}
    target={{ month: "2026-10-01", total_target: "15000", nifty_target: "8000", midcap_target: "5000", smallcap_target: "2000" }} />);
  expect(screen.getByText("Portfolio allocation")).toBeInTheDocument();
  expect(screen.getByText("Needs classification")).toBeInTheDocument();
  expect(screen.getByText("₹8,897.41 · 100.00%")).toBeInTheDocument();
  expect(screen.getByText("Target allocation")).toBeInTheDocument();
});
it("intraday card labels reliable closed position and realised P&L", async () => {
  const { IntradayCard } = await import("./components/IntradayCard");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    date: "2026-10-07", observed_at: "2026-10-07T10:00:00Z", positions_available: true,
    positions: [{ symbol: "NYKAA", exchange: "NSE", product: "MIS", buy_quantity: 5, sell_quantity: 5,
      open_quantity: 0, buy_value: "500", sell_value: "550", realised_pnl: "50", unrealised_pnl: "0",
      status: "CLOSED", source: "provider_positions", fill_count: 2 }]
  })));
  render(<IntradayCard revision={0} />);
  expect(await screen.findByText("Closed position")).toBeInTheDocument();
  expect(screen.getByText("Realised P&L ₹50.00")).toBeInTheDocument();
});
it("classified backend allocation has no needs-classification row or trading controls", async () => {
  const { Allocation } = await import("./components/Plan");
  render(<Allocation summary={{ ...summary, holdings_market_value: "1000", allocation: {
    NIFTY_50: "0", LARGE_CAP: "600", MID_CAP: "200", SMALL_CAP: "200", OTHER: "0", UNCLASSIFIED: "0"
  } }} />);
  expect(screen.queryByText("Needs classification")).not.toBeInTheDocument();
  expect(screen.queryByText(/Some holdings need classification/)).not.toBeInTheDocument();
  expect(screen.getByText("₹600.00 · 60.00%")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});


it.each(["portfolio", "detail"])("shows T1 delivery ownership in %s", async (page) => {
  const holding = {
    tradingsymbol: "HDFCSML250", exchange: "NSE", bucket: "SMALL_CAP",
    quantity: 0, t1_quantity: 3, effective_quantity: 3,
    average_price: "180.12", last_price: "181.13",
    invested_value: "540.36", current_value: "543.39",
    unrealised_pnl: "3.03", unrealised_pnl_percent: "0.560737", synced_at: null,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    new Response(JSON.stringify(String(input).includes("/history") ? [] : [holding])));
  render(
    <MemoryRouter initialEntries={[page === "detail" ? "/holding/HDFCSML250" : "/portfolio"]}>
      <Routes>
        <Route path="/portfolio" element={<Portfolio revision={0} />} />
        <Route path="/holding/:symbol" element={<HoldingDetail revision={0} />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText("₹540.36")).toBeInTheDocument();
  expect(screen.getByText("₹543.39")).toBeInTheDocument();
  expect(screen.getByText("3", { selector: page === "detail" ? "strong" : "td" })).toBeInTheDocument();
});
