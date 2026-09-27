/**
 * Application shell: header, navigation, account menu and route outlet.
 */

import { NavLink, Outlet } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { api } from "../api/client";
import { UserMenu } from "./UserMenu";
import "./layout.css";

export function AppShell() {
  const runtime = useApi(() => api.getRuntime(), []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <NavLink to="/" className="brand" aria-label="PyCraft home">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">PyCraft</span>
        </NavLink>

        <nav className="app-nav" aria-label="Main">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            Dashboard
          </NavLink>
          <NavLink
            to="/challenges"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Challenges
          </NavLink>
          <NavLink to="/roadmap" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            Roadmap
          </NavLink>
        </nav>

        <div className="runtime-badge" title="Execution environment">
          {runtime.data ? (
            <>
              <span className="runtime-dot" data-backend={runtime.data.execution_backend} />
              <span className="runtime-label">Python {runtime.data.default_python_version}</span>
            </>
          ) : (
            <span className="runtime-label muted">connecting…</span>
          )}
        </div>

        <UserMenu />
      </header>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
