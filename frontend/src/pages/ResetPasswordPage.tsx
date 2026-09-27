/**
 * Complete a password reset.
 *
 * The token arrives as `?token=` in a link from the reset email. The route is
 * public: by definition the user is signed out when they use it. On success we
 * send them to `/login`, because the backend revokes every session.
 */

import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button, Notice } from "../components";
import { Field, PasswordChecklist, TextInput } from "../components/FormField";
import { useApi } from "../hooks/useApi";
import { assessPassword } from "../auth/passwordPolicy";
import "../auth/auth.css";
import "./authPages.css";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const config = useApi(() => api.getAuthConfig(), []);

  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const minLength = config.data?.min_password_length ?? 10;
  const assessment = useMemo(() => assessPassword(password, minLength), [password, minLength]);
  const mismatch = confirm !== "" && confirm !== password;

  if (token === "") {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Reset link is incomplete</h1>
          <p className="auth-sub">
            This page needs the token from your reset email. Open the link in the message again, or
            request a new one.
          </p>
          <div className="auth-footer">
            <Link to="/forgot-password">Request a new link</Link>
            <Link to="/login">Back to sign in</Link>
          </div>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Password updated</h1>
          <p className="auth-sub">
            Your password has been changed and every existing session was signed out. Sign in with
            the new password.
          </p>
          <div className="auth-footer">
            <Link to="/login">Sign in</Link>
          </div>
        </div>
      </div>
    );
  }

  const canSubmit = assessment.satisfied && confirm === password && !busy;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setBusy(true);
    try {
      await api.confirmPasswordReset({ token, password });
      setDone(true);
      window.setTimeout(() => {
        navigate("/login", { replace: true });
      }, 2500);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The password could not be updated. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <header className="auth-head">
          <h1>Choose a new password</h1>
          <p className="auth-sub">Reset links are single-use and expire after an hour.</p>
        </header>

        {error !== null && (
          <div className="auth-notice">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}

        <form className="auth-form" onSubmit={onSubmit} noValidate>
          <Field label="New password">
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
                  autoFocus
                  disabled={busy}
                />
                <PasswordChecklist assessment={assessment} id={`${id}-checklist`} />
              </>
            )}
          </Field>

          <Field
            label="Confirm password"
            error={mismatch ? "Passwords do not match" : null}
          >
            {({ id, describedBy, invalid }) => (
              <TextInput
                id={id}
                describedBy={describedBy}
                invalid={invalid}
                type="password"
                value={confirm}
                onChange={setConfirm}
                autoComplete="new-password"
                disabled={busy}
              />
            )}
          </Field>

          <Button type="submit" variant="primary" busy={busy} disabled={!canSubmit}>
            {busy ? "Updating…" : "Update password"}
          </Button>

          <div className="auth-links">
            <Link to="/forgot-password">Request a new link</Link>
            <Link to="/login">Back to sign in</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
