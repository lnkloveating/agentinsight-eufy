import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

import { useProjectsQuery } from '../../shared/api/hooks';
import { api } from '../../shared/api/client';

export function AppShellLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectsQuery = useProjectsQuery();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ projectId: string; x: number; y: number } | null>(null);
  const queryClient = useQueryClient();
  const [deleting, setDeleting] = useState(false);

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

  useEffect(() => {
    if (!contextMenu) return undefined;
    function close() { setContextMenu(null); }
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [contextMenu]);

  async function handleDeleteProject(projectId: string) {
    setDeleting(true);
    try {
      await api.deleteProject(projectId);
      await queryClient.invalidateQueries({ queryKey: ['projects'] });
      if (activeProject === projectId) navigate('/projects');
    } finally {
      setDeleting(false);
      setContextMenu(null);
    }
  }

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
                {projectItems.map((item) => (
                  <div
                    className={`app-shell__project-item${activeProject === item.id ? ' active' : ''}`}
                    key={item.id}
                  >
                    <button
                      className="app-shell__project-item-name"
                      onClick={() => { setActiveProject(item.id); navigate(`/projects/${item.id}`); }}
                      type="button"
                    >
                      {item.name}
                    </button>
                    <button
                      className="app-shell__project-item-more"
                      onClick={(e) => {
                        e.stopPropagation();
                        const rect = (e.target as HTMLElement).getBoundingClientRect();
                        setContextMenu({ projectId: item.id, x: rect.right, y: rect.bottom });
                      }}
                      type="button"
                      aria-label="更多操作"
                    >
                      <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
                        <circle cx="4" cy="8" r="1.5" />
                        <circle cx="8" cy="8" r="1.5" />
                        <circle cx="12" cy="8" r="1.5" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="app-shell__nav-divider" />

          <p className="app-shell__nav-section-title">场景验证</p>

          <button
            className={`app-shell__nav-row app-shell__nav-row--secondary${scenariosMatch ? ' active' : ''}`}
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

          <div className="app-shell__nav-steps">
            <button
              className={`app-shell__nav-step done${location.search === '?page=brief' ? ' active' : ''}`}
              onClick={() => navigate('/projects?page=brief')}
              type="button"
            >
              <i className="app-shell__nav-step-dot" />
              <span>项目简报</span>
            </button>
            <button
              className={`app-shell__nav-step done${location.search === '?page=research' ? ' active' : ''}`}
              onClick={() => navigate('/projects?page=research')}
              type="button"
            >
              <i className="app-shell__nav-step-dot" />
              <span>实时调研</span>
            </button>
            <button
              className={`app-shell__nav-step done${location.search === '?page=evidence' ? ' active' : ''}`}
              onClick={() => navigate('/projects?page=evidence')}
              type="button"
            >
              <i className="app-shell__nav-step-dot" />
              <span>证据中心</span>
            </button>
            <button
              className={`app-shell__nav-step done${location.search === '?page=users' ? ' active' : ''}`}
              onClick={() => navigate('/projects?page=users')}
              type="button"
            >
              <i className="app-shell__nav-step-dot" />
              <span>AI 用户替身</span>
            </button>
            <button
              className={`app-shell__nav-step done${location.search === '?page=concepts' ? ' active' : ''}`}
              onClick={() => navigate('/projects?page=concepts')}
              type="button"
            >
              <i className="app-shell__nav-step-dot" />
              <span>概念竞技场</span>
            </button>
          </div>

          <button
            className={`app-shell__nav-row app-shell__nav-row--secondary${metricsMatch ? ' active' : ''}`}
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
            className={`app-shell__nav-row app-shell__nav-row--secondary${reportMatch ? ' active' : ''}`}
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

      {contextMenu ? (
        <div
          className="app-shell__context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            className="app-shell__context-menu-item"
            disabled={deleting}
            onClick={() => { void handleDeleteProject(contextMenu.projectId); }}
            type="button"
          >
            删除
          </button>
        </div>
      ) : null}
    </div>
  );
}
