import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom';

import { useProjectsQuery } from '../../shared/api/hooks';

export function AppShellLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectsQuery = useProjectsQuery();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [activeProject, setActiveProject] = useState<string | null>(null);

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
  const metricsHref = resolvedProjectId ? `/projects/${resolvedProjectId}/metrics` : '/projects';
  const reportHref = resolvedProjectId ? `/projects/${resolvedProjectId}/report` : '/projects';

  useEffect(() => {
    if (currentProjectId) setActiveProject(currentProjectId);
    else if (location.pathname === '/projects') {
      const params = new URLSearchParams(location.search);
      if (params.get('page') === 'create') setActiveProject(null);
    }
  }, [location, currentProjectId]);

  const projectItems = useMemo(() => {
    const projects = projectsQuery.data ?? [];
    return [...projects]
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      .map((p) => ({ id: p.project_id, name: p.brief.category }));
  }, [projectsQuery.data]);

  return (
    <div className={`app-shell${sidebarCollapsed ? ' app-shell--sidebar-collapsed' : ''}`}>
      <aside className="app-shell__sidebar">
        <div className="app-shell__sidebar-top">
          <div className="app-shell__brand">
            <p>AGENTINSIGHT × eufy</p>
          </div>
          <button
            aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
            className="app-shell__collapse"
            onClick={() => setSidebarCollapsed((current) => !current)}
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d={sidebarCollapsed ? 'M9 18l6-6-6-6' : 'M15 18l-6-6 6-6'} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <nav className="app-shell__nav" aria-label="主导航">
          <p className="app-shell__nav-section-title">工作区</p>

          <div
            className={`app-shell__nav-row${projectsExpanded ? ' app-shell__nav-row--expanded' : ''}`}
            onClick={() => setProjectsExpanded((current) => !current)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setProjectsExpanded((current) => !current); } }}
            role="button"
            tabIndex={0}
            aria-expanded={projectsExpanded}
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M3 10.6 12 3l9 7.6V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V10.6Z" />
            </svg>
            <span>我的项目</span>
            <svg className={`app-shell__chevron${projectsExpanded ? ' app-shell__chevron--open' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m7 10 5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>

          {projectsExpanded ? (
            <div className="app-shell__projects-panel">
              <div className="app-shell__projects-head">
                <span>Projects</span>
                <button
                  aria-label="新建项目"
                  className="app-shell__add-btn"
                  onClick={() => navigate('/projects?page=create')}
                  title="新建项目"
                  type="button"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 5v14M5 12h14" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
              <div className="app-shell__project-list">
                {projectItems.map((item, i) => (
                  <button
                    className={`app-shell__project-item${activeProject === item.id ? ' active' : ''}`}
                    key={item.id}
                    onClick={() => { setActiveProject(item.id); navigate(`/projects/${item.id}`); }}
                    type="button"
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="app-shell__nav-divider" />

          <p className="app-shell__nav-section-title">场景验证</p>

          <button
            className="app-shell__nav-row app-shell__nav-row--secondary"
            onClick={() => navigate(`${resolvedProjectId ? `/projects/${resolvedProjectId}/scenarios` : '/projects'}`)}
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
              <rect x="14" y="14" width="7" height="7" rx="1" />
            </svg>
            <span>场景实验</span>
          </button>

          <div className="app-shell__nav-divider" />

          <p className="app-shell__nav-section-title">产品发现</p>

          <button
            className="app-shell__nav-row app-shell__nav-row--secondary"
            onClick={() => navigate(metricsHref)}
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="3" y="13" width="4" height="8" rx="1" />
              <rect x="10" y="8" width="4" height="13" rx="1" />
              <rect x="17" y="3" width="4" height="18" rx="1" />
            </svg>
            <span>指标</span>
          </button>

          <button
            className="app-shell__nav-row app-shell__nav-row--secondary"
            onClick={() => navigate(reportHref)}
            type="button"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M6 2h8l5 5v15H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.8V8h4.2L13 3.8Z" />
            </svg>
            <span>报告</span>
          </button>
        </nav>
      </aside>

      <div className="app-shell__content">
        <Outlet />
      </div>
    </div>
  );
}
