import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { ProjectMetricsPage } from '../pages/ProjectMetricsPage';
import { ProjectReportPage } from '../pages/ProjectReportPage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ProjectWorkbenchPage } from '../pages/ProjectWorkbenchPage';
import { ScenarioVerificationPage } from '../pages/ScenarioVerificationPage';
import { AppShellLayout } from '../widgets/app-shell/AppShellLayout';

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate replace to="/projects" />} />
          <Route element={<AppShellLayout />}>
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectWorkbenchPage />} />
            <Route path="/projects/:projectId/report" element={<ProjectReportPage />} />
            <Route path="/projects/:projectId/metrics" element={<ProjectMetricsPage />} />
            <Route path="/projects/:projectId/scenarios" element={<ScenarioVerificationPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
