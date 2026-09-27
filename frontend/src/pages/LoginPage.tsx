/**
 * Sign-in page.
 *
 * The destination comes from the guard's redirect state, so a deep link that
 * bounced through `/login` resumes where the user was headed.
 */

import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, githubAuthorizeUrl } from "../api/client";
import { Button, Notice } from "../components";
import { Field, TextInput } from "../components/FormField";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../auth/AuthContext";
import "../auth/auth.css";
import "./authPages.css";

interface FromState {
  from?: { pathname?: string; search?: string };
}

/** Same-site path only: an injected `state.from` must not become an open redirect. */
function resolveDestination(from: FromState["from"]): string {
  const path = from?.pathname;
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) return "/";
  return `${path}${from?.search ?? ""}`;
}

/**
 * Read the message the GitHub callback put in the query string.
 *
 * The backend sends a single percent-encoded `error` parameter. Older builds
 * nested a `reason=` inside it, so that shape is still tolerated rather than
 * showing the user a raw `reason=...` prefix.
 */
function readOAuthError(params: URLSearchParams): string | null {
  const raw = params.get("error");
  if (raw === null || raw === "") return null;

  const nested = new URLSearchParams(raw).get("reason");
  if (nested !== null && nested !== "") return nested;

  return raw.startsWith("reason=") ? raw.slice("reason=".length) : raw;
}

export function LoginPage() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const config = useApi(() => api.getAuthConfig(), []);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const destination = resolveDestination((location.state as FromState | null)?.from);

  if (status === "authenticated") return <Navigate to={destination} replace />;

  const oauthError = readOAuthError(params);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(destination, { replace: true });
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const passwordAuthEnabled = config.data?.password_auth_enabled ?? true;

  return (
    <div className="auth-page">
      <div className="auth-card">
        <header className="auth-head">
          <h1>Sign in</h1>
          <p className="auth-sub">Continue your engineering track.</p>
        </header>

        {oauthError !== null && <Notice tone="danger">{oauthError}</Notice>}

        {error !== null && (
          <div className="auth-notice">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}

        {config.error !== null && (
          <div className="auth-notice">
            <Notice tone="warning">
              Sign-in options could not be loaded. Password sign-in is shown by default.
            </Notice>
          </div>
        )}

        {passwordAuthEnabled && (
          <form className="auth-form" onSubmit={onSubmit} noValidate>
            <Field label="Email">
              {({ id, describedBy, invalid }) => (
                <TextInput
                  id={id}
                  describedBy={describedBy}
                  invalid={invalid}
                  type="email"
                  value={email}
                  onChange={setEmail}
                  autoComplete="email"
                  placeholder="you@example.com"
                  disabled={busy}
                />
              )}
            </Field>

            <Field label="Password">
              {({ id, describedBy, invalid }) => (
                <TextInput
                  id={id}
                  describedBy={describedBy}
                  invalid={invalid}
                  type="password"
                  value={password}
                  onChange={setPassword}
                  autoComplete="current-password"
                  disabled={busy}
                />
              )}
            </Field>

            <Button type="submit" busy={busy} disabled={email === "" || password === ""}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>

            <div className="auth-links">
              <Link to="/forgot-password">Forgot password?</Link>
            </div>
          </form>
        )}

        {!passwordAuthEnabled && config.data?.github_enabled !== true && (
          <Notice tone="warning">
            No sign-in method is enabled on this deployment. Contact an administrator.
          </Notice>
        )}

        {config.data?.github_enabled === true && (
          <>
            {passwordAuthEnabled && <div className="auth-divider">or</div>}
            <a className="auth-oauth" href={githubAuthorizeUrl(destination)}>
              <GitHubMark />
              Continue with GitHub
            </a>
          </>
        )}

        <footer className="auth-footer">
          <p>New to PyCraft?</p>
          {config.data?.registration_enabled === false ? (
            <span className="auth-footer-note">Registration is currently closed.</span>
          ) : (
            <Link to="/register">Create an account</Link>
          )}
        </footer>
      </div>
    </div>
  );
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
      />
    </svg>
  );
}
