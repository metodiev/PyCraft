/**
 * Application routes.
 *
 * The workspace is a sibling of the dashboard rather than a child, because it
 * takes over the full viewport instead of the reading column.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { ChallengeList } from "./pages/ChallengeList";
import { ChallengeWorkspace } from "./pages/ChallengeWorkspace";
import { RoadmapPage } from "./pages/RoadmapPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="challenges" element={<ChallengeList />} />
        <Route path="challenges/:challengeId" element={<ChallengeWorkspace />} />
        <Route path="roadmap" element={<RoadmapPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
