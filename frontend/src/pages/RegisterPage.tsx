/**
 * Account creation.
 *
 * The password checklist mirrors the backend policy from `/auth/config`; the
 * submit button stays disabled until every rule passes, which keeps the common
 * 422 away without duplicating validation logic in the form.
 */

import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button, Card, Notice, Skeleton } from "../components";
import { Field, PasswordChecklist, TextInput } from "../components/FormField";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../auth/AuthContext";
import { assessPassword } from "../auth/passwordPolicy";
import "../auth/auth.css";
import "./authPages.css";

export function RegisterPage() {
  const { status, register } = useAuth();
  const navigate = useNavigate();
  const config = useApi(() => api.getAuthConfig(), []);

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const minLength = config.data?.min_password_length ?? 10;
  const assessment = useMemo(() => assessPassword(password, minLength), [password, minLength]);

  if (status === "authenticated") return <Navigate to="/" replace />;

  if (config.loading) {
    return (
      <div className="auth-page">
        <Card className="auth-card" as="div">
          <Skeleton height="1.75rem" width="180px" />
          <div className="auth-loading-gap" />
          <Skeleton height="2.25rem" />
          <div className="auth-loading-gap" />
          <Skeleton height="2.25rem" />
          <div className="auth-loading-gap" />
          <Skeleton height="2.25rem" />
        </Card>
      </div>
    );
  }

  if (config.data === null) {
    return (
      <div className="auth-page">
        <Card className="auth-card" as="div">
          <h1 className="auth-title">Registration unavailable</h1>
          <p className="auth-sub">
            The sign-in options could not be loaded, so a new account cannot be created right now.
          </p>
          <div className="auth-notice">
            <Notice tone="danger">{config.error ?? "Unexpected error"}</Notice>
          </div>
          <div className="auth-links">
            <button className="link-button" onClick={config.reload}>
              Try again
            </button>
            <Link to="/login">Back to sign in</Link>
          </div>
        </Card>
      </div>
    );
  }

  if (!config.data.registration_enabled) {
    return (
      <div className="auth-page">
        <Card className="auth-card" as="div">
          <h1 className="auth-title">Registration is closed</h1>
          <p className="auth-sub">
            This deployment does not accept new accounts. An administrator can create one for you.
          </p>
          <div className="auth-footer">
            <Link to="/login">Back to sign in</Link>
          </div>
        </Card>
      </div>
    );
  }

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const canSubmit = emailValid && assessment.satisfied && !busy;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setBusy(true);
    try {
      await register(email.trim(), password, displayName.trim());
      navigate("/", { replace: true });
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Registration failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <header className="auth-head">
          <h1>Create account</h1>
          <p className="auth-sub">Track XP, streaks and skill mastery as you progress.</p>
        </header>

        {error !== null && (
          <div className="auth-notice">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}

        <form className="auth-form" onSubmit={onSubmit} noValidate>
          <Field
            label="Email"
            error={email !== "" && !emailValid ? "Enter a valid email address" : null}
          >
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

          <Field label="Display name" optional hint="Defaults to your email handle.">
            {({ id, describedBy, invalid }) => (
              <TextInput
                id={id}
                describedBy={describedBy}
                invalid={invalid}
                value={displayName}
                onChange={setDisplayName}
                autoComplete="nickname"
                maxLength={80}
                disabled={busy}
              />
            )}
          </Field>

          <Field
            label="Password"
            hint={password === "" ? `At least ${minLength} characters.` : undefined}
          >
            {({ id, describedBy, invalid }) => (
              <>
                <TextInput
                  id={id}
                  describedBy={[describedBy, `${id}-checklist`].filter(Boolean).join(" ")}
                  invalid={invalid}
                  type="password"
                  value={password}
                  onChange={setPassword}
                  autoComplete="new-password"
                  disabled={busy}
                />
                <PasswordChecklist assessment={assessment} id={`${id}-checklist`} />
              </>
            )}
          </Field>

          <Button type="submit" variant="primary" busy={busy} disabled={!canSubmit}>
            {busy ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <footer className="auth-footer">
          <p>Already have an account?</p>
          <Link to="/login">Sign in</Link>
        </footer>
      </div>
    </div>
  );
}
