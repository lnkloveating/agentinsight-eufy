import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom';

import { useCreateProjectMutation, useProjectsQuery } from '../../shared/api/hooks';
import type { ResearchBrief } from '../../shared/types/api';
import { AppNavLink, Button } from '../../shared/ui/primitives';
import { ProjectCreationPanel } from './WorkbenchComponents';

function SidebarIcon({ kind }: { kind: 'home' | 'project' | 'metrics' | 'report' | 'create' | 'workspace' | 'currentProject' | 'scenario' }) {
  if (kind === 'home') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M2.5 7.25L8 2.75L13.5 7.25V13.25H9.75V9.75H6.25V13.25H2.5V7.25Z" />
      </svg>
    );
  }

  if (kind === 'workspace') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M2 2.75H7.25V7.5H2V2.75ZM8.75 2.75H14V7.5H8.75V2.75ZM2 8.5H7.25V13.25H2V8.5ZM8.75 8.5H14V13.25H8.75V8.5Z" />
      </svg>
    );
  }

  if (kind === 'currentProject') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M2.5 3.75H6.25L7.5 5.25H13.5V12.25H2.5V3.75ZM4 5V11H12V6.75H6.75L5.5 5.25H4Z" />
      </svg>
    );
  }

  if (kind === 'scenario') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M3.25 2.75H12.75V13.25H3.25V2.75ZM4.5 4V12H11.5V4H4.5ZM6 6.5H10V7.75H6V6.5ZM6 9H10V10.25H6V9Z" />
      </svg>
    );
  }

  if (kind === 'project') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M3 3.25H13V5H3V3.25ZM3 7.125H9.5V8.875H3V7.125ZM3 11H11.5V12.75H3V11Z" />
      </svg>
    );
  }

  if (kind === 'metrics') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M3 12.75V8.5H5V12.75H3ZM7 12.75V5.25H9V12.75H7ZM11 12.75V2.75H13V12.75H11Z" />
      </svg>
    );
  }

  if (kind === 'report') {
    return (
      <svg aria-hidden="true" viewBox="0 0 16 16">
        <path d="M4 2.75H9.75L12.5 5.5V13.25H4V2.75ZM9.25 3.75V6H11.5" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 16 16">
      <path d="M7.25 3V7.25H3V8.75H7.25V13H8.75V8.75H13V7.25H8.75V3H7.25Z" />
    </svg>
  );
}

export function AppShellLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectsQuery = useProjectsQuery();
  const createProjectMutation = useCreateProjectMutation();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const projectMatch = useMatch('/projects/:projectId');
  const reportMatch = useMatch('/projects/:projectId/report');
  const metricsMatch = useMatch('/projects/:projectId/metrics');
  const scenariosMatch = useMatch('/projects/:projectId/scenarios');
  const currentProjectId = projectMatch?.params.projectId ?? reportMatch?.params.projectId ?? metricsMatch?.params.projectId ?? scenariosMatch?.params.projectId;

  const latestProject = useMemo(() => {
    const projects = projectsQuery.data ?? [];
    return [...projects].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))[0];
  }, [projectsQuery.data]);

  const resolvedProjectId = currentProjectId ?? latestProject?.project_id;
  const resolvedProject = (projectsQuery.data ?? []).find((item) => item.project_id === resolvedProjectId);
  const metricsHref = resolvedProjectId ? `/projects/${resolvedProjectId}/metrics` : '/projects';
  const reportHref = resolvedProjectId ? `/projects/${resolvedProjectId}/report` : '/projects';
  const scenariosHref = resolvedProjectId ? `/projects/${resolvedProjectId}/scenarios` : '/projects';

  useEffect(() => {
    setSheetOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!sheetOpen) {
      return undefined;
    }

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        setSheetOpen(false);
      }
    }

    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [sheetOpen]);

  async function handleCreate(brief: ResearchBrief): Promise<void> {
    const project = await createProjectMutation.mutateAsync({ brief });
    setSheetOpen(false);
    navigate(`/projects/${project.project_id}`);
  }

  return (
    <div className={`app-shell${sidebarCollapsed ? ' app-shell--sidebar-collapsed' : ''}`}>
      <aside className="app-shell__sidebar">
        <div className="app-shell__sidebar-top">
          <div className="app-shell__brand">
            <p>AgentInsight × eufy</p>
          </div>

          <button
            aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
            className="app-shell__collapse"
            onClick={() => setSidebarCollapsed((current) => !current)}
            type="button"
          >
            <span className="app-shell__nav-icon" aria-hidden="true">
              <svg viewBox="0 0 16 16">
                {sidebarCollapsed ? (
                  <path d="M6 3.5L10 8L6 12.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
                ) : (
                  <path d="M10 3.5L6 8L10 12.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
                )}
              </svg>
            </span>
          </button>
        </div>

        <nav className="app-shell__nav" aria-label="主导航">
          <div className="app-shell__nav-group">
            <p className="app-shell__nav-section-title">工作区</p>
            <AppNavLink end to="/projects">
              <span className="app-shell__nav-icon">
                <SidebarIcon kind="home" />
              </span>
              <span className="app-shell__nav-label">我的项目</span>
            </AppNavLink>
          </div>
          <div className="app-shell__nav-group">
            <p className="app-shell__nav-section-title">当前项目</p>
            {(projectsQuery.data ?? []).map((project) => (
              <AppNavLink key={project.project_id} end to={`/projects/${project.project_id}`}>
                <span className="app-shell__nav-icon">
                  <SidebarIcon kind="project" />
                </span>
                <span className="app-shell__nav-label">{project.brief.category}</span>
              </AppNavLink>
            ))}
          </div>
          <div className="app-shell__nav-group">
            <p className="app-shell__nav-section-title">场景验证</p>
            {(resolvedProject?.brief.scenarios ?? []).map((scenario) => (
              <AppNavLink key={scenario} end to={scenariosHref}>
                <span className="app-shell__nav-icon">
                  <SidebarIcon kind="scenario" />
                </span>
                <span className="app-shell__nav-label">{scenario}</span>
              </AppNavLink>
            ))}
          </div>
          <div className="app-shell__nav-divider" />
          <AppNavLink end to={metricsHref}>
            <span className="app-shell__nav-icon">
              <SidebarIcon kind="metrics" />
            </span>
            <span className="app-shell__nav-label">指标</span>
          </AppNavLink>
          <AppNavLink end to={reportHref}>
            <span className="app-shell__nav-icon">
              <SidebarIcon kind="report" />
            </span>
            <span className="app-shell__nav-label">报告</span>
          </AppNavLink>
        </nav>

        <div className="app-shell__sidebar-footer">
          <Button onClick={() => navigate('/projects?page=create')}>
            <span className="app-shell__nav-icon">
              <SidebarIcon kind="create" />
            </span>
            <span className="app-shell__nav-label">新建研究</span>
          </Button>
        </div>
      </aside>

      <div className="app-shell__content">
        <Outlet />
      </div>

      {sheetOpen ? (
        <div className="sheet-backdrop" role="presentation" onClick={() => setSheetOpen(false)}>
          <section
            aria-label="新建研究"
            className="sheet-panel"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sheet-panel__header">
              <div>
                <p className="section-heading__eyebrow">Create Project</p>
                <h2>新建研究</h2>
              </div>
              <button className="sheet-panel__close" onClick={() => setSheetOpen(false)} type="button">
                关闭
              </button>
            </div>
            <ProjectCreationPanel embedded busy={createProjectMutation.isPending} onSubmit={handleCreate} />
          </section>
        </div>
      ) : null}
    </div>
  );
}
