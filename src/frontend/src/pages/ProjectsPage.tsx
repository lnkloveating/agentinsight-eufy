import { useProjectsQuery } from '../shared/api/hooks';
import { formatDateTime } from '../shared/lib/format';
import { ContinueWorkingPanel, NextActionPanel, ProjectActivityRail } from '../widgets/home/HomeDashboardSections';

export function ProjectsPage() {
  const projectsQuery = useProjectsQuery();
  const projects = projectsQuery.data ?? [];
  const activeProjects = projects.filter((project) =>
    ['researching', 'supplementing_research', 'generating_report'].includes(project.status),
  ).length;
  const pendingDecisions = projects.filter((project) => project.pending_decision).length;
  const completedProjects = projects.filter((project) => project.status === 'completed').length;
  const latestUpdatedAt = [...projects]
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))[0]
    ?.updated_at;

  return (
    <main className="screen screen--home">
      <section className="screen__hero screen__hero--home">
        <div className="home-intro">
          <div className="home-intro__copy">
            <p className="home-intro__eyebrow">AgentInsight × eufy</p>
          </div>
          <div className="overview-strip" aria-label="工作台总览">
            <div className="overview-strip__item">
              <span>待审批</span>
              <strong>{pendingDecisions}</strong>
            </div>
            <div className="overview-strip__item">
              <span>进行中</span>
              <strong>{activeProjects}</strong>
            </div>
            <div className="overview-strip__item">
              <span>已完成</span>
              <strong>{completedProjects}</strong>
            </div>
            <div className="overview-strip__item overview-strip__item--wide">
              <span>最近更新</span>
              <strong>{latestUpdatedAt ? formatDateTime(latestUpdatedAt) : '暂无项目'}</strong>
            </div>
          </div>
        </div>
      </section>

      <div className="home-flow">
        <NextActionPanel projects={projects} />
        <ContinueWorkingPanel projects={projects} />
        <ProjectActivityRail projects={projects} />
      </div>
    </main>
  );
}
