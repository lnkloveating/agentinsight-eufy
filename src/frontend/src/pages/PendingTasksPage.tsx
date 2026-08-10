import { Link } from 'react-router-dom';

import { useProjectsQuery } from '../shared/api/hooks';
import { formatDateTime } from '../shared/lib/format';
import type { Project } from '../shared/types/api';
import { EmptyState } from '../shared/ui/primitives';

type PendingTask = {
  id: string;
  project: Project;
  title: string;
};

function getDecisionTitle(project: Project): string {
  switch (project.pending_decision?.gate) {
    case 'brief':
      return '确认项目简报';
    case 'concept':
      return '确认概念晋级';
    case 'final':
      return '完成最终审批';
    default:
      return '处理项目决策';
  }
}

function getPendingTasks(projects: Project[]): PendingTask[] {
  return projects
    .flatMap((project) => {
      if (project.pending_decision) {
        return [{
          id: `${project.project_id}-decision`,
          project,
          title: getDecisionTitle(project),
        }];
      }

      if (project.status === 'failed') {
        return [{
          id: `${project.project_id}-recovery`,
          project,
          title: '排查研究失败节点',
        }];
      }

      if (project.status === 'supplementing_research') {
        return [{
          id: `${project.project_id}-evidence`,
          project,
          title: '补齐研究证据',
        }];
      }

      return [];
    })
    .sort((left, right) => Date.parse(right.project.updated_at) - Date.parse(left.project.updated_at));
}

export function PendingTasksPage() {
  const projectsQuery = useProjectsQuery();
  const tasks = getPendingTasks(projectsQuery.data ?? []);

  if (projectsQuery.isLoading) {
    return <main className="screen"><EmptyState title="正在读取待处理事项" description="正在汇总所有项目的审批、补证和失败恢复任务。" /></main>;
  }

  if (projectsQuery.isError) {
    return <main className="screen"><EmptyState title="无法读取待处理事项" description="请检查后端服务状态后重试。" /></main>;
  }

  return (
    <main className="screen pending-tasks-page">
      <header className="pending-tasks-page__header">
        <div>
          <p className="section-heading__eyebrow">Decision Inbox</p>
          <div className="pending-tasks-page__title-row">
            <h1 className="pending-tasks-page__title">待处理</h1>
            <div className="pending-tasks-page__summary">
              <strong>{tasks.length}</strong>
              <span>项待处理</span>
            </div>
          </div>
        </div>
      </header>

      {tasks.length === 0 ? (
        <section className="ui-card pending-tasks-page__empty">
          <strong>当前没有待处理事项</strong>
          <p>所有项目暂时都在正常推进。</p>
        </section>
      ) : (
        <section className="pending-tasks-list" aria-label="所有待处理事项">
          {tasks.map((task) => (
            <article className="ui-card pending-task-card" key={task.id}>
              <div className="pending-task-card__marker" aria-hidden="true" />
              <div className="pending-task-card__main">
                <div className="pending-task-card__meta">
                  <span>{task.project.brief.category}</span>
                </div>
                <h2>{task.title}</h2>
                <span className="pending-task-card__time">最近更新：{formatDateTime(task.project.updated_at)}</span>
              </div>
              <div className="pending-task-card__side">
                <Link className="ui-button ui-button--primary" to={`/projects/${task.project.project_id}`}>
                  去处理
                </Link>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
