import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AppShell } from "@/layout/AppShell";
import { HomePage } from "@/pages/HomePage";
import { ProjectPage } from "@/pages/ProjectPage";
import { DrillTab } from "@/pages/project/DrillTab";
import { OverviewTab } from "@/pages/project/OverviewTab";
import { PlaceholderTab } from "@/pages/project/PlaceholderTab";

export function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="projects/:slug" element={<ProjectPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<OverviewTab />} />
            <Route path="drill" element={<DrillTab />} />
            <Route
              path="bom"
              element={
                <PlaceholderTab
                  title="Bill of Materials"
                  description="Editable table with inline cell edits, Import from PDF, and polarity-sensitivity flags."
                />
              }
            />
            <Route
              path="bench"
              element={
                <PlaceholderTab
                  title="Bench mode"
                  description="Grouped build-along checklist with polarity hints and progress tracking."
                />
              }
            />
            <Route
              path="debug"
              element={
                <PlaceholderTab
                  title="Debug helper"
                  description="Per-IC expected voltages and triage for a silent first power-up."
                />
              }
            />
          </Route>
        </Route>
      </Routes>
    </Router>
  );
}
