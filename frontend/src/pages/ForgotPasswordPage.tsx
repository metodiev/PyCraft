/**
 * Password reset request.
 *
 * The backend never discloses whether an address is registered, so the page must
 * behave identically for every outcome — including a failed request. Showing a
 * different message would leak exactly what the API is designed to hide.
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Button, Notice } from "../components";
import { Field, TextInput } from "../components/FormField";
import "../auth/auth.css";
import "./authPages.css";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || email.trim() === "") return;
    setBusy(true);
    try {
      await api.requestPasswordReset({ email: email.trim() });
    } catch {
      // Deliberately swallowed: see the module comment.
    } finally {
      setBusy(false);
      setSubmitted(true);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <header className="auth-head">
          <h1>Reset your password</h1>
          <p className="auth-sub">
            Enter the email address on your account and we will send a reset link.
          </p>
        </header>

        {submitted ? (
          <>
            <Notice tone="info">
              If that email address is registered, a reset link is on its way. The link expires
              shortly, so use it soon.
            </Notice>
            <p className="auth-note">
              Nothing arrived? Check your spam folder, or sign in with a linked provider such as
              GitHub.
            </p>
            <div className="auth-footer">
              <Link to="/login">Back to sign in</Link>
              <button
                className="link-button"
                onClick={() => {
                  setSubmitted(false);
                }}
              >
                Use a different address
              </button>
            </div>
          </>
        ) : (
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
                  autoFocus
                />
              )}
            </Field>

            <Button type="submit" variant="primary" busy={busy} disabled={email.trim() === ""}>
              {busy ? "Sending…" : "Send reset link"}
            </Button>
          </form>
        )}

        {!submitted && (
          <footer className="auth-footer">
            <Link to="/login">Back to sign in</Link>
          </footer>
        )}
      </div>
    </div>
  );
}
