/**
 * Header account menu.
 *
 * A button plus state rather than `<details>`: the popup has to close on outside
 * clicks and on Escape, and a native disclosure element cannot do that without
 * the same listeners. Keyboard users get Escape, Tab-out and a focus-visible
 * ring; the trigger advertises its state through `aria-expanded`.
 */

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Avatar } from "./FormField";
import { useAuth } from "../auth/AuthContext";

export function UserMenu() {
  const { user, status, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const container = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent | TouchEvent) {
      const target = event.target;
      if (target instanceof Node && container.current?.contains(target) === true) return;
      setOpen(false);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (status === "loading") {
    return <div className="user-menu-placeholder" aria-hidden="true" />;
  }

  if (status === "anonymous" || user === null) {
    return (
      <div className="header-auth">
        <Link to="/login" className="nav-link">
          Sign in
        </Link>
        <Link to="/register" className="header-cta" aria-label="Create account">
          {/* Two labels so the button fits a narrow header; the accessible name
              comes from aria-label, which stays stable as the text changes. */}
          <span className="cta-label cta-full" aria-hidden="true">
            Create account
          </span>
          <span className="cta-label cta-short" aria-hidden="true">
            Sign up
          </span>
        </Link>
      </div>
    );
  }

  async function onSignOut() {
    setBusy(true);
    try {
      await logout();
      setOpen(false);
      navigate("/login", { replace: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="user-menu" ref={container}>
      <button
        ref={trigger}
        type="button"
        className="user-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <Avatar name={user.display_name} email={user.email} src={user.avatar_url} size={26} />
        <span className="user-menu-name">{user.display_name}</span>
        <span className="user-menu-caret" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div className="user-menu-popup" role="menu" aria-label="Account">
          <div className="user-menu-head">
            <span className="user-menu-head-name">{user.display_name}</span>
            <span className="user-menu-head-email">{user.email}</span>
          </div>
          <Link
            to="/profile"
            role="menuitem"
            className="user-menu-item"
            onClick={() => setOpen(false)}
          >
            Profile
          </Link>
          <button
            type="button"
            role="menuitem"
            className="user-menu-item"
            disabled={busy}
            onClick={() => void onSignOut()}
          >
            {busy ? "Signing out…" : "Sign out"}
          </button>
        </div>
      )}
    </div>
  );
}
