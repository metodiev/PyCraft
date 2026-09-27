/**
 * Route guard for pages that require a session.
 *
 * While the stored token is still being validated the guard renders a skeleton:
 * redirecting during that window would flash the login page at every reload of
 * a signed-in user.
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { Card, Skeleton } from "../components";
import { useAuth } from "./AuthContext";
import "./auth.css";

export function RequireAuth({ children }: { children?: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <AuthLoading />;

  if (status === "anonymous") {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children ?? <Outlet />}</>;
}

/** Placeholder that keeps the shell stable while the session is resolved. */
export function AuthLoading() {
  return (
    <Card className="auth-loading" as="div">
      <Skeleton height="1.5rem" width="220px" />
      <div className="auth-loading-gap" />
      <Skeleton height="1rem" />
      <div className="auth-loading-gap" />
      <Skeleton height="1rem" width="70%" />
    </Card>
  );
}
