import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../auth";
import { ErrorBanner } from "../components/ui";

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") await login(username, password);
      else await register(username, email, password);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="brand brand-large">
          <span className="brand-mark">✓</span>
          <div>
            <strong>AI Workflow Rescue</strong>
            <small>Detect, investigate and safely recover failed workflows</small>
          </div>
        </div>

        <h1>{mode === "signin" ? "Sign in" : "Create an account"}</h1>

        <form onSubmit={submit} className="form">
          <label>
            {mode === "signin" ? "Username or email" : "Username"}
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              autoFocus
              minLength={mode === "register" ? 3 : undefined}
              maxLength={mode === "register" ? 30 : undefined}
              pattern={mode === "register" ? "[A-Za-z0-9_]{3,30}" : undefined}
              title={mode === "register" ? "3–30 letters, digits or underscores" : undefined}
            />
          </label>

          {mode === "register" && (
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
          )}

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              required
              minLength={mode === "register" ? 12 : undefined}
            />
            {mode === "register" && <small className="muted">At least 12 characters.</small>}
          </label>

          <ErrorBanner message={error} />

          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="muted center">
          {mode === "signin" ? "New here?" : "Already registered?"}{" "}
          <button
            className="link"
            onClick={() => {
              setMode(mode === "signin" ? "register" : "signin");
              setError(null);
            }}
          >
            {mode === "signin" ? "Create an account" : "Sign in"}
          </button>
        </p>
        {mode === "register" && (
          <p className="muted center small">New accounts are operators. Admins are created by the operator of the system.</p>
        )}
      </div>
    </div>
  );
}
