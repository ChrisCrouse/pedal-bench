import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AppShell } from "@/layout/AppShell";
import { HomePage } from "@/pages/HomePage";
import { ProjectPage } from "@/pages/ProjectPage";
import { DecoderPage } from "@/pages/DecoderPage";
import { InventoryPage } from "@/pages/InventoryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { BOMTab } from "@/pages/project/BOMTab";
import { BenchTab } from "@/pages/project/BenchTab";
import { DebugTab } from "@/pages/project/DebugTab";
import { DrillTab } from "@/pages/project/DrillTab";
import { OverviewTab } from "@/pages/project/OverviewTab";

export function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="decoder" element={<DecoderPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="projects/:slug" element={<ProjectPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<OverviewTab />} />
            <Route path="drill" element={<DrillTab />} />
            <Route path="bom" element={<BOMTab />} />
            <Route path="bench" element={<BenchTab />} />
            <Route path="debug" element={<DebugTab />} />
          </Route>
        </Route>
      </Routes>
    </Router>
  );
}
