import { it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { clearSession, validateAuthTransport } from "./api/auth";

const session = { authenticated: true, csrf_token: "test-csrf", expires_at: null };
function responses(authenticated = false, invalid = false) {
  clearSession();
  let signedIn = authenticated;
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.endsWith("/auth/login")) {
      if (invalid) return new Response("sensitive backend details", { status: 401 });
      signedIn = true;
      expect(init?.credentials).toBe("include");
      return new Response(JSON.stringify(session));
    }
    if (path.endsWith("/auth/logout")) {
      expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("test-csrf");
      signedIn = false;
      return new Response(JSON.stringify({ authenticated: false, csrf_token: null, expires_at: null }));
    }
    if (path.endsWith("/auth/session")) return new Response(JSON.stringify(signedIn ? session : { authenticated: false, csrf_token: null, expires_at: null }));
    if (path.endsWith("/monthly-target")) return new Response(JSON.stringify({ month: "2026-10-01", total_target: "15000", nifty_target: "8000", midcap_target: "5000", smallcap_target: "2000" }));
    if (path.endsWith("/status")) return new Response(JSON.stringify({ connection_status: "expired", token_valid: false, refresh_required: false }));
    if (path.endsWith("/activity/today")) return new Response(JSON.stringify({ executed: [], orders: [], awaiting_holdings: [], open_pending_count: 0, rejected_cancelled_count: 0 }));
    return new Response(JSON.stringify([]));
  });
}
function renderApp() { render(<MemoryRouter><App /></MemoryRouter>); }
it("shows household login and performs no private requests while unauthenticated", async () => {
  const fetch = responses(); renderApp();
  expect(await screen.findByLabelText("Username")).toBeInTheDocument();
  expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", { name: "Connect Zerodha for today" })).not.toBeInTheDocument();
});
it("valid dashboard session renders distinct Zerodha reconnect UI", async () => {
  responses(true); renderApp();
  expect(await screen.findByRole("button", { name: "Connect Zerodha for today" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
});
it("successful login verifies cookie session before displaying dashboard", async () => {
  responses(); renderApp();
  fireEvent.change(await screen.findByLabelText("Username"), { target: { value: "test-household" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument();
});
it("failed login has generic message and clears password", async () => {
  responses(false, true); renderApp();
  fireEvent.change(await screen.findByLabelText("Username"), { target: { value: "test-household" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to sign in. Check your username and password.");
  expect(screen.getByLabelText("Password")).toHaveValue("");
  expect(screen.queryByText(/sensitive backend/)).not.toBeInTheDocument();
});
it("logout returns to household login", async () => {
  responses(true); renderApp();
  fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
  expect(await screen.findByLabelText("Username")).toBeInTheDocument();
});
it("expired private session unmounts financial pages and returns to login", async () => {
  const fetch=responses(true); renderApp();
  await screen.findByRole("button", { name: "Sign out" });
  fetch.mockResolvedValue(new Response(JSON.stringify({ detail: { error: "dashboard_auth_required" } }), { status: 401 }));
  fireEvent.click(screen.getByRole("button", { name: "↻ Refresh" }));
  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
});

it("refuses HTTP password transport from an HTTPS dashboard", () => {
  expect(() => validateAuthTransport("https:", "http://127.0.0.1:8000")).toThrow("Dashboard API must use HTTPS.");
  expect(() => validateAuthTransport("https:", "https://api.example.com")).not.toThrow();
  expect(() => validateAuthTransport("http:", "http://127.0.0.1:8000")).not.toThrow();
});
