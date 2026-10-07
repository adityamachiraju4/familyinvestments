import { baseUrl } from "./client";
export interface DashboardSession {
  authenticated: boolean;
  csrf_token: string | null;
  expires_at: string | null;
}
let csrf = "";
export function csrfHeaders(): Record<string, string> {
  return csrf ? { "X-CSRF-Token": csrf } : {};
}
export function clearSession() { csrf = ""; }
export function validateAuthTransport(pageProtocol: string, apiUrl: string) {
  if (pageProtocol === "https:" && new URL(apiUrl, `${pageProtocol}//dashboard.invalid`).protocol !== "https:")
    throw new Error("Dashboard API must use HTTPS.");
}
async function authRequest(path: string, body?: unknown): Promise<DashboardSession> {
  validateAuthTransport(window.location.protocol, baseUrl);
  const response = await fetch(baseUrl + "/auth/" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "include", signal: AbortSignal.timeout(20000),
    headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...csrfHeaders() },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }).catch(() => { throw new Error("Unable to reach the dashboard. Please try again."); });
  if (!response.ok) throw new Error(path === "login" ? (response.status === 429 ? "Too many login attempts. Try again later." : "Unable to sign in. Check your username and password.") : "Unable to verify dashboard access. Please try again.");
  const result = await response.json().catch(() => { throw new Error("Unable to verify dashboard access. Please try again."); }) as DashboardSession;
  csrf = result.csrf_token || "";
  return result;
}
export const dashboardAuth = {
  session: () => authRequest("session"),
  login: async (username: string, password: string) => {
    await authRequest("login", { username, password });
    const session = await authRequest("session");
    if (!session.authenticated) throw new Error("Your browser could not save the login cookie. Use the configured dashboard domain and allow its cookies.");
    return session;
  },
  logout: () => authRequest("logout", {}),
};
