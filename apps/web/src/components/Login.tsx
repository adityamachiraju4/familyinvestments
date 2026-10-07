import { useState, type FormEvent } from "react";
import { dashboardAuth, type DashboardSession } from "../api/auth";
export function Login({ onLogin, initialError }: { onLogin: (value: DashboardSession) => void; initialError: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try { onLogin(await dashboardAuth.login(username, password)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to sign in. Please try again."); }
    finally { setPassword(""); setBusy(false); }
  }
  return <div className="login-shell"><section className="login-card">
    <p className="eyebrow">FAMILY INVESTMENTS</p>
    <h1>Your family’s perspective.</h1>
    <p className="muted">Sign in to your private household dashboard.</p>
    <form onSubmit={submit}>
      <label htmlFor="dashboard-username">Username</label>
      <input id="dashboard-username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required maxLength={128} />
      <label htmlFor="dashboard-password">Password</label>
      <input id="dashboard-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={1024} />
      {error && <p role="alert" className="notice">{error}</p>}
      <button className="refresh" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
    <p className="note">Dashboard login protects your family’s information. Your Zerodha connection is managed separately after you sign in.</p>
  </section></div>;
}
