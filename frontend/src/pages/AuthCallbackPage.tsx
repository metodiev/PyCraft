/**
 * Landing page for the GitHub OAuth redirect.
 *
 * The backend hands tokens over in the URL **fragment**, which never reaches a
 * server. They are read once, written to the token store, and stripped from the
 * address bar with `history.replaceState` so a copied link or a browser-history
 * entry cannot leak them. The user's intended destination arrives separately in
 * `?next=`, which keeps it out of the fragment the backend controls.
 */

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { Notice } from "../components";
import type { TokenInput } from "../auth/tokenStore";
import { useAuth } from "../auth/AuthContext";
import "../auth/auth.css";
import "./authPages.css";

/** Same-site path only, so neither the fragment nor `next` can redirect off-site. */
function safeDestination(value: string | null): string {
  if (value === null || !value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}

function readFragment(): { tokens: TokenInput | null; error: string | null } {
  const raw = globalThis.location.hash.startsWith("#")
    ? globalThis.location.hash.slice(1)
    : globalThis.location.hash;

  const params = new URLSearchParams(raw);
  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token");
  const error = params.get("error") ?? params.get("reason");

  if (error !== null && error !== "") return { tokens: null, error };
  if (accessToken === null || refreshToken === null) return { tokens: null, error: null };

  const expires = Number(params.get("expires_in") ?? "0");
  return {
    tokens: {
      access_token: accessToken,
      refresh_token: refreshToken,
      token_type: params.get("token_type") ?? "bearer",
      expires_in: Number.isFinite(expires) ? expires : 0,
    },
    error: null,
  };
}

export function AuthCallbackPage() {
  const { acceptTokens, status } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [failure, setFailure] = useState<string | null>(null);
  const [missingTokens, setMissingTokens] = useState(false);
  // React 19 StrictMode runs effects twice in development; the fragment is
  // single-use, so the exchange must happen exactly once per mount.
  const handled = useRef(false);

  const destination = safeDestination(params.get("next"));

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const { tokens: incoming, error } = readFragment();
    // Strip the fragment immediately: it is read above and must not survive in
    // history, bookmarks or a shared URL.
    globalThis.history.replaceState(
      globalThis.history.state,
      "",
      globalThis.location.pathname + globalThis.location.search,
    );

    if (error !== null) {
      setFailure(error);
      return;
    }
    if (incoming === null) {
      setMissingTokens(true);
      return;
    }

    acceptTokens(incoming)
      .then(() => navigate(destination, { replace: true }))
      .catch((cause: unknown) => {
        setFailure(
          cause instanceof ApiError
            ? cause.message
            : "The sign-in could not be completed. Please try again.",
        );
      });
  }, [acceptTokens, navigate, destination]);

  if (failure !== null) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">GitHub sign-in failed</h1>
          <div className="auth-notice">
            <Notice tone="danger">{failure}</Notice>
          </div>
          <div className="auth-footer">
            <Link to="/login">Back to sign in</Link>
          </div>
        </div>
      </div>
    );
  }

  if (missingTokens) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Nothing to sign in with</h1>
          <p className="auth-sub">
            This page expects the credentials that GitHub sign-in appends to the URL. Start the
            sign-in again from the login page.
          </p>
          <div className="auth-footer">
            <Link to="/login">Back to sign in</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Finishing sign-in…</h1>
        <p className="auth-sub">
          {status === "authenticated"
            ? "Redirecting to your dashboard."
            : "Verifying your GitHub account and creating your session."}
        </p>
        <div className="auth-loading-gap" />
        <div className="auth-footer">
          <Link to="/login">Back to sign in</Link>
        </div>
      </div>
    </div>
  );
}
