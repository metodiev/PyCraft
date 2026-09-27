/**
 * Application routes.
 *
 * The app shell wraps every page; inside it a guard decides whether the reader
 * needs a session. Public auth routes stay outside the guard so `/login` is
 * reachable while signed out.
 *
 * The workspace is a sibling of the dashboard rather than a child, because it
 * takes over the full viewport instead of the reading column.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RequireAuth } from "./auth/RequireAuth";
import { Dashboard } from "./pages/Dashboard";
import { ChallengeList } from "./pages/ChallengeList";
import { ChallengeWorkspace } from "./pages/ChallengeWorkspace";
import { RoadmapPage } from "./pages/RoadmapPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { ProfilePage } from "./pages/ProfilePage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        {/* Public: someone signed out must be able to reach these. */}
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="forgot-password" element={<ForgotPasswordPage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
        <Route path="auth/callback" element={<AuthCallbackPage />} />

        {/* Protected: progress is per-user, so these need a session. */}
        <Route element={<RequireAuth />}>
          <Route index element={<Dashboard />} />
          <Route path="challenges" element={<ChallengeList />} />
          <Route path="challenges/:challengeId" element={<ChallengeWorkspace />} />
          <Route path="roadmap" element={<RoadmapPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
