import { dashboardAuth, clearSession, type DashboardSession } from "./api/auth";
import { Login } from "./components/Login";
import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, reconnect, refreshPortfolio } from "./api/client";
import { useQuery } from "./hooks/useQuery";
import { dateLabel } from "./utils/format";
import Overview from "./pages/Overview";
import Portfolio from "./pages/Portfolio";
import HoldingDetail from "./pages/HoldingDetail";
import Investments from "./pages/Investments";
import History from "./pages/History";
function DashboardShell({ onLogout, callbackResult }: { onLogout: () => Promise<void>; callbackResult: string | null }) {
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const status = useQuery(api.status, revision);
  const [sessionExpired, setSessionExpired] = useState(false);
  useEffect(() => {
    const expire = () => setSessionExpired(true);
    window.addEventListener("zerodha-session-expired", expire);
    return () => window.removeEventListener("zerodha-session-expired", expire);
  }, []);
  const connected =
    status.data?.connection_status === "connected" &&
    status.data.token_valid !== false &&
    !sessionExpired;
  const inFlight = useRef(false);
  const automaticAttempted = useRef(false);
  const refresh = useCallback(async (automatic = false) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setMessage("");
    try {
      const result = await refreshPortfolio(automatic);
      if (!automatic || result.status === "ok")
        setMessage("Portfolio refreshed successfully.");
      setSessionExpired(false);
    } catch (error) {
      if (!(
        error instanceof Error && error.message === "Zerodha connection expired"
      )) {
        setMessage(
          error instanceof Error
            ? error.message
            : "Refresh failed. Please try again.",
        );
      }
    } finally {
      setRevision((v) => v + 1);
      inFlight.current = false;
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    if (
      !status.loading &&
      status.data?.token_valid &&
      connected &&
      !automaticAttempted.current
    ) {
      automaticAttempted.current = true;
      if (callbackResult === "connected" || status.data.refresh_required) void refresh(true);
    }
  }, [status.loading, status.data, connected, refresh, callbackResult]);
  async function connect() {
    try {
      await reconnect();
    } catch {
      setMessage("Unable to open Zerodha login. Please try again.");
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <LinkBrand />
        <nav aria-label="Main navigation">
          {["Overview", "Portfolio", "Investments", "History"].map(
            (label, i) => (
              <NavLink
                end={i === 0}
                to={i === 0 ? "/" : `/${label.toLowerCase()}`}
                key={label}
              >
                <span className="nav-icon">{["◫", "▤", "◈", "◷"][i]}</span>
                {label}
              </NavLink>
            ),
          )}
        </nav>
        <div className="sidebar-footer">
          <span className="monogram">FI</span>
          <div>
            Built for your family<small>Perspective. Patience. Progress.</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <span className="header-title">Family Investments</span>
          <div className="header-actions">
            <button className="refresh" disabled={logoutBusy} onClick={async () => {
              setLogoutBusy(true);
              try { await onLogout(); } catch { setMessage("Unable to sign out. Please try again."); }
              finally { setLogoutBusy(false); }
            }}>{logoutBusy ? "Signing out…" : "Sign out"}</button>
            <div className="connection">
              <span className={`dot ${connected ? "connected" : ""}`} />
              {status.loading
                ? "Checking Zerodha…"
                : connected
                  ? "Zerodha Connected"
                  : "Zerodha connection expired"}
              <small>
                Last synced{" "}
                {dateLabel(
                  status.data?.last_refresh_at || status.data?.last_sync_at,
                  true,
                )}
              </small>
            </div>
            <button
              className="refresh"
              disabled={busy}
              onClick={() => void refresh()}
            >
              {busy ? "Refreshing…" : "↻ Refresh"}
            </button>
          </div>
        </header>
        <main>
          {callbackResult && <p className="notice" role="status">{callbackResult === "connected"
            ? "Zerodha connected successfully."
            : "Zerodha connection could not be completed. Please try again."}</p>}
          {message && (
            <p className="notice" role="status">
              {message}
            </p>
          )}
          {!status.loading && !connected && (
            <p className="connection-note" role="status">
              <span>{status.error || "Zerodha connection expired"}</span>
              <button className="refresh" onClick={connect}>
                Connect Zerodha for today
              </button>
            </p>
          )}
          <Routes>
            <Route
              path="/"
              element={
                <Overview
                  revision={revision}
                  canFetchSummary={!status.loading && connected}
                />
              }
            />
            <Route
              path="/portfolio"
              element={<Portfolio revision={revision} />}
            />
            <Route
              path="/portfolio/:symbol"
              element={<HoldingDetail revision={revision} />}
            />
            <Route
              path="/investments"
              element={<Investments revision={revision} />}
            />
            <Route path="/history" element={<History revision={revision} />} />
            <Route
              path="*"
              element={
                <p>
                  Page not found. Use the navigation to return to your
                  dashboard.
                </p>
              }
            />
          </Routes>
          <footer>
            Family Investments{" "}
            <span>For the life you’re building together.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
function LinkBrand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        f<span>i</span>
      </span>
      <div>
        Family
        <br />
        Investments
      </div>
    </div>
  );
}


export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [callbackResult] = useState(() => {
    const marker = new URLSearchParams(location.search).get("zerodha");
    return marker === "connected" || marker === "connect_failed" ? marker : null;
  });
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (!params.has("zerodha")) return;
    params.delete("zerodha");
    navigate({ pathname: location.pathname, search: params.toString() ? `?${params}` : "", hash: location.hash }, { replace: true });
  }, [location.pathname, location.search, location.hash, navigate]);
  const [session, setSession] = useState<DashboardSession | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const expire = () => { clearSession(); setSession(null); setChecking(false); setError(""); };
    window.addEventListener("dashboard-session-expired", expire);
    dashboardAuth.session().then(value => { if (active) setSession(value); })
      .catch(() => { if (active) setError("Unable to verify dashboard access. Please try again."); })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; window.removeEventListener("dashboard-session-expired", expire); };
  }, []);
  useEffect(() => {
    if (!session?.authenticated || !session.expires_at) return;
    const timeout = window.setTimeout(() => { clearSession(); setSession(null); }, Math.max(0, Date.parse(session.expires_at) - Date.now()));
    return () => window.clearTimeout(timeout);
  }, [session]);
  if (checking) return <div className="login-shell"><p role="status">Checking dashboard access…</p></div>;
  if (!session?.authenticated) return <Login initialError={error} onLogin={setSession} />;
  return <DashboardShell callbackResult={callbackResult} onLogout={async () => { await dashboardAuth.logout(); clearSession(); setSession(null); }} />;
}
