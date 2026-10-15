import { FormEvent, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, getBackendBaseUrl } from "../api/client";
import { saveToken } from "../store/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [checkingBackend, setCheckingBackend] = useState(false);
  const [sessionNotice] = useState(() => {
    const msg = sessionStorage.getItem("sessionExpiredMessage");
    if (msg) sessionStorage.removeItem("sessionExpiredMessage");
    return msg;
  });

  const checkBackend = useCallback(() => {
    setCheckingBackend(true);
    api.checkBackendHealth().then((ok) => {
      setBackendOnline(ok);
      setCheckingBackend(false);
    }).catch(() => {
      setBackendOnline(false);
      setCheckingBackend(false);
    });
  }, []);

  useEffect(() => {
    checkBackend();
  }, [checkBackend]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await api.login(username, password);
      const token = response?.access_token;
      if (!token || typeof token !== "string") {
        setError("Invalid response from server. Please try again.");
        return;
      }
      saveToken(token);
      navigate("/", { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      setError(message);
      if (message.toLowerCase().includes("failed to fetch") || message.toLowerCase().includes("network")) {
        setError(`${message}. Ensure the backend is running (e.g. http://localhost:8000).`);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page login-page--split">
      <aside className="login-panel-left">
        <div className="login-panel-left-inner">
          <h1 className="login-panel-title">Attendance<br />Management System</h1>
          <p className="login-panel-subtitle">Accurate, automatic attendance for staff and students.</p>
          <div className="login-panel-badges">
            <span>Face recognition</span>
            <span>Shifts &amp; leave</span>
            <span>Reports</span>
          </div>
          <section className="login-panel-section">
            <h3 className="login-panel-section-title">
              <span className="login-panel-icon login-panel-icon--lightning" aria-hidden>⚡</span>
              Attendance Highlights
            </h3>
            <ul className="login-panel-list">
              <li><span className="login-panel-check" aria-hidden>✓</span> Punches captured automatically from face readers and devices</li>
              <li><span className="login-panel-check" aria-hidden>✓</span> Late, half-day, absent and leave worked out from shift rules</li>
              <li><span className="login-panel-check" aria-hidden>✓</span> Leave requests, manual entries and on-duty approvals in one place</li>
              <li><span className="login-panel-check" aria-hidden>✓</span> Staff and students grouped by department and year</li>
            </ul>
          </section>
          <section className="login-panel-section">
            <h3 className="login-panel-section-title">
              <span className="login-panel-check login-panel-check--circle" aria-hidden>✓</span>
              Why Teams Use It
            </h3>
            <ul className="login-panel-list">
              <li><span className="login-panel-check" aria-hidden>✓</span> Live dashboard of who is in, late or absent today</li>
              <li><span className="login-panel-check" aria-hidden>✓</span> Monthly registers, late and overtime, and leave balance reports</li>
              <li><span className="login-panel-check" aria-hidden>✓</span> Export to CSV or PDF for payroll and audits</li>
              <li><span className="login-panel-check" aria-hidden>✓</span> Self-service portal for employees to check attendance and apply for leave</li>
            </ul>
          </section>
        </div>
      </aside>

      <div className="login-panel-right">
        <div className="login-panel-right-inner">
          {sessionNotice && (
            <div className="login-backend-alert" role="alert">
              <strong>{sessionNotice}</strong>
            </div>
          )}
          {backendOnline === false && (
            <div className="login-backend-alert" role="alert">
              <strong>Backend is not reachable.</strong> Start the API server, then click Recheck.
              <div className="login-backend-alert-actions">
                <a href={getBackendBaseUrl() + "/health"} target="_blank" rel="noreferrer">Open {getBackendBaseUrl()}/health</a>
                <button type="button" onClick={checkBackend} disabled={checkingBackend}>
                  {checkingBackend ? "Checking…" : "Recheck connection"}
                </button>
              </div>
            </div>
          )}
          <header className="login-page-header">
            <h1>Attendance Management System</h1>
          </header>
          <div className="login-card">
            <h2 className="login-card-title">Welcome back</h2>
            <p className="login-card-subtitle">Enter your credentials to access the dashboard.</p>
            <form className="login-card-form" onSubmit={submit}>
              <label className="login-card-label">User Name</label>
              <input
                className="login-card-input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
              />
              <label className="login-card-label">Password</label>
              <input
                className="login-card-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
              />
              {error && <p className="login-card-error" role="alert">{error}</p>}
              <button
                type="submit"
                className="login-card-submit"
                disabled={loading || backendOnline === false}
              >
                {loading ? "Signing in…" : "Login to Dashboard"}
                <span className="login-card-submit-arrow" aria-hidden>→</span>
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
