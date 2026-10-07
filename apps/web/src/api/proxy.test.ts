import { afterEach, expect, it, vi } from "vitest";
import config from "../../vercel.json";

afterEach(() => { vi.unstubAllEnvs(); vi.restoreAllMocks(); vi.resetModules(); });

it("uses same-origin production API despite a legacy environment override", async () => {
  vi.stubEnv("PROD", true);
  vi.stubEnv("VITE_API_BASE_URL", "https://legacy.invalid");
  vi.resetModules();
  expect((await import("./client")).baseUrl).toBe("/api");
});

it("supports the local development default and override", async () => {
  vi.stubEnv("PROD", false);
  vi.stubEnv("VITE_API_BASE_URL", "");
  vi.resetModules();
  expect((await import("./client")).baseUrl).toBe("http://127.0.0.1:8000");
  vi.stubEnv("VITE_API_BASE_URL", "http://localhost:9000/");
  vi.resetModules();
  expect((await import("./client")).baseUrl).toBe("http://localhost:9000");
});

it("routes auth, portfolio mutations and reconnect through the proxy with credentials and CSRF", async () => {
  vi.stubEnv("PROD", true);
  vi.resetModules();
  const { dashboardAuth, validateAuthTransport, csrfHeaders } = await import("./auth");
  const { api, refreshPortfolio, reconnect } = await import("./client");
  expect(() => validateAuthTransport("https:", "/api")).not.toThrow();
  expect(() => validateAuthTransport("https:", "http://unsafe.invalid")).toThrow();
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/logout")) return new Response(JSON.stringify({ authenticated: false, csrf_token: null }));
    if (url.includes("/auth/")) return new Response(JSON.stringify({ authenticated: true, csrf_token: "session-csrf" }));
    // Reject the returned URL before navigation, after verifying initiation.
    if (url.includes("/zerodha/login")) return new Response(JSON.stringify({ login_url: "https://unsafe.invalid" }));
    return new Response(JSON.stringify({ status: "ok" }));
  });
  await dashboardAuth.login("household", "test-password");
  await api.summary(); await api.holdings(); await api.status();
  await refreshPortfolio();
  await expect(reconnect()).rejects.toThrow("safely");
  await dashboardAuth.logout();
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    "/api/auth/login", "/api/auth/session", "/api/portfolio/summary",
    "/api/portfolio/holdings", "/api/integrations/zerodha/status",
    "/api/portfolio/refresh", "/api/integrations/zerodha/login?return_to_dashboard=true",
    "/api/auth/logout",
  ]);
  for (const [, init] of fetch.mock.calls) expect(init?.credentials).toBe("include");
  for (const [, init] of fetch.mock.calls.slice(1))
    expect(init?.headers).toMatchObject({ "X-CSRF-Token": "session-csrf" });
  expect(fetch.mock.calls[5][1]?.method).toBe("POST");
  expect(fetch.mock.calls[7][1]?.method).toBe("POST");
  expect(csrfHeaders()).toEqual({});
});

it("scopes the external rewrite to API paths and strips the prefix", () => {
  expect(config.rewrites).toEqual([{
    source: "/api/:path*",
    destination: "https://familyinvestments-production.up.railway.app/:path*",
  }]);
});
