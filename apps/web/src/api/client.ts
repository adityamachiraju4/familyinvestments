import { csrfHeaders, clearSession } from "./auth";
import type {
  Summary,
  Intraday,
  Snapshot,
  Target,
  Status,
  Holding,
  HoldingHistory,
  Activity,
  Contributions,
  RefreshResult,
} from "./types";
export const baseUrl = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
export async function request<T>(
  path: string,
  method = "GET",
  timeout = 20000,
): Promise<T> {
  try {
    const response = await fetch(baseUrl + path, {
      method,
      signal: AbortSignal.timeout(timeout),
      credentials: "include",
      headers: { Accept: "application/json", ...csrfHeaders() },
    });
    if (response.status === 401) {
      const body = await response.json().catch(() => ({}));
      if (body.error === "credentials_invalid") {
        window.dispatchEvent(new Event("zerodha-session-expired"));
        throw new Error("Zerodha connection expired");
      }
      clearSession();
      window.dispatchEvent(new Event("dashboard-session-expired"));
      throw new Error("Dashboard login required");
    }
    if (!response.ok) throw new Error("Unable to load portfolio data. Please try again.");
    return (await response.json()) as T;
  } catch (error) {
    if (
      error instanceof Error &&
      (error.message.startsWith("Zerodha connection expired") || error.message === "Dashboard login required")
    )
      throw error;
    throw new Error("Unable to load portfolio data. Please try again.");
  }
}
export const api = {
  intraday: () => request<Intraday>("/portfolio/intraday/today"),
  activity: () => request<Activity>("/portfolio/activity/today"),
  contributions: () => request<Contributions>("/portfolio/contributions/month"),
  summary: () => request<Summary>("/portfolio/summary"),
  snapshots: (limit = 30) =>
    request<Snapshot[]>(`/portfolio/snapshots?limit=${limit}`),
  target: () => request<Target>("/portfolio/monthly-target"),
  status: () => request<Status>("/integrations/zerodha/status"),
  holdings: () => request<Holding[]>("/portfolio/holdings"),
  history: (symbol: string) =>
    request<HoldingHistory[]>(
      `/portfolio/holdings/${encodeURIComponent(symbol)}/history?limit=3650`,
    ),
};
export async function refreshPortfolio(ifStale = false) {
  const result = await request<RefreshResult>(
    `/portfolio/refresh${ifStale ? "?if_stale=true" : ""}`,
    "POST",
    65000,
  );
  if (result.status === "reconnect_required") {
    window.dispatchEvent(new Event("zerodha-session-expired"));
    throw new Error("Zerodha connection expired");
  }
  return result;
}
export async function reconnect() {
  const { login_url } = await request<{ login_url: string }>(
    "/integrations/zerodha/login?return_to_dashboard=true",
  );
  const url = new URL(login_url);
  if (url.protocol !== "https:" || url.hostname !== "kite.zerodha.com")
    throw new Error("Unable to open Zerodha login safely.");
  window.location.assign(url.href);
}
