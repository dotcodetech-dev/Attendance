import { FormEvent, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, getBackendBaseUrl } from "../api/client";
import { saveToken } from "../store/auth";

// Vendor support shown under the login card.
const SUPPORT_PHONE = "9488810882";
const SUPPORT_EMAIL = "dotcodetech@gmail.com";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="lp">
      {/* Mild pastel shapes and small "pixel" squares (echoing the Dotcode logo). Decoration only. */}
      <div className="lp-deco" aria-hidden="true">
        <span className="lp-shape lp-shape--mint" />
        <span className="lp-shape lp-shape--peach" />
        <span className="lp-shape lp-shape--lavender" />
        <span className="lp-shape lp-shape--sky" />
        <span className="lp-shape lp-shape--butter" />
        <span className="lp-pixel lp-pixel--1" />
        <span className="lp-pixel lp-pixel--2" />
        <span className="lp-pixel lp-pixel--3" />
        <span className="lp-pixel lp-pixel--4" />
        <span className="lp-pixel lp-pixel--5" />
        <span className="lp-pixel lp-pixel--6" />
      </div>

      <main className="lp-main">
        {sessionNotice && (
          <div className="lp-alert" role="alert">
            <strong>{sessionNotice}</strong>
          </div>
        )}
        {backendOnline === false && (
          <div className="lp-alert" role="alert">
            <strong>Backend is not reachable.</strong> Start the API server, then click Recheck.
            <div className="lp-alert-actions">
              <a href={getBackendBaseUrl() + "/health"} target="_blank" rel="noreferrer">Open {getBackendBaseUrl()}/health</a>
              <button type="button" onClick={checkBackend} disabled={checkingBackend}>
                {checkingBackend ? "Checking…" : "Recheck connection"}
              </button>
            </div>
          </div>
        )}

        <div className="lp-card">
          <div className="lp-card-strip" aria-hidden="true"><span /><span /><span /><span /></div>
          <div className="lp-card-body">
            <div className="lp-head">
              <div className="lp-mark">
                {/* Face recognition: a face inside scan corners. */}
                <svg aria-hidden="true" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 8V6a2 2 0 0 1 2-2h2" /><path d="M16 4h2a2 2 0 0 1 2 2v2" />
                  <path d="M20 16v2a2 2 0 0 1-2 2h-2" /><path d="M8 20H6a2 2 0 0 1-2-2v-2" />
                  <path d="M9 9.5v1" /><path d="M15 9.5v1" /><path d="M12 9.5v3.5h-1" />
                  <path d="M9.5 15.5c1.4 1.1 3.6 1.1 5 0" />
                </svg>
              </div>
              <p className="lp-eyebrow">Code <b>Easy</b> Attendance Management System</p>
              <h1 className="lp-title">Welcome back</h1>
              <p className="lp-sub">Sign in to see today's attendance.</p>
            </div>

            <form className="lp-form" onSubmit={submit}>
              <div className="lp-field">
                <label htmlFor="lp-user">User name</label>
                <div className="lp-input-wrap">
                  <svg className="lp-input-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="8" r="4" /><path d="M4 20c1.5-3.6 4.6-5.5 8-5.5s6.5 1.9 8 5.5" />
                  </svg>
                  <input
                    id="lp-user"
                    className="lp-input"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Enter your user name"
                    autoComplete="username"
                    autoFocus
                  />
                </div>
              </div>

              <div className="lp-field">
                <label htmlFor="lp-pass">Password</label>
                <div className="lp-input-wrap">
                  <svg className="lp-input-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="5" y="11" width="14" height="9" rx="2.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" />
                  </svg>
                  <input
                    id="lp-pass"
                    className="lp-input lp-input--pw"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                  />
                  <button type="button" className="lp-eye" onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>
                    {showPassword ? (
                      <svg aria-hidden="true" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 3l18 18" /><path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 8.5 4 9.5 6-.4.9-1.2 2.1-2.4 3.2" />
                        <path d="M6.6 6.6C4.6 7.9 3.2 9.8 2.5 12c1 2 4.5 6 9.5 6 1.6 0 3-.4 4.3-1" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
                      </svg>
                    ) : (
                      <svg aria-hidden="true" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M2.5 12C3.5 10 7 6 12 6s8.5 4 9.5 6c-1 2-4.5 6-9.5 6s-8.5-4-9.5-6z" /><circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {error && <p className="lp-error" role="alert">{error}</p>}

              <button type="submit" className="lp-submit" disabled={loading || backendOnline === false}>
                {loading ? "Signing in…" : "Sign in"}
                {!loading && (
                  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14" /><path d="M13 6l6 6-6 6" />
                  </svg>
                )}
              </button>
            </form>
          </div>
        </div>

        <footer className="lp-support">
          <span className="lp-support-badge">
            <img className="lp-support-logo" src="/branding/dotcode-logo.webp" alt="Dotcode Technology" width={158} height={44} />
          </span>
          <p className="lp-support-title">Need help? Contact support</p>
          <div className="lp-support-links">
            <a href={`tel:+91${SUPPORT_PHONE}`}>
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />
              </svg>
              {SUPPORT_PHONE}
            </a>
            <a href={`mailto:${SUPPORT_EMAIL}`}>
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="M3.5 6.5l8.5 6.5 8.5-6.5" />
              </svg>
              {SUPPORT_EMAIL}
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}
