import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatDateTime } from '../../shared/lib/format';
import { STATUS_LABELS } from '../../shared/lib/project';
import type { Project } from '../../shared/types/api';
import { Badge } from '../../shared/ui/primitives';

function getProjectBadgeTone(status: Project['status']): 'accent' | 'warning' | 'danger' | 'success' {
  if (status === 'failed' || status === 'terminated') {
    return 'danger';
  }

  if (status === 'completed') {
    return 'success';
  }

  if (status === 'awaiting_brief_approval' || status === 'awaiting_concept_approval' || status === 'awaiting_final_approval') {
    return 'warning';
  }

  return 'accent';
}

function getDecisionGateLabel(project: Project): string {
  if (project.pending_decision?.gate === 'brief') {
    return 'Brief';
  }

  if (project.pending_decision?.gate === 'concept') {
    return 'Concept';
  }

  if (project.pending_decision?.gate === 'final') {
    return 'Final';
  }

  return project.pending_decision?.gate ?? 'Review';
}

function getStageLabel(stage: string): string {
  const stageMap: Record<string, string> = {
    brief_confirmation: 'Brief 确认阶段',
    research_planning: '研究计划阶段',
    concept_synthesis: '概念综合阶段',
    report_generation: '提案生成阶段',
    final_review: '最终审批阶段',
  };

  return stageMap[stage] ?? stage.replaceAll('_', ' ');
}

function getProjectShortCode(project: Project): string {
  return project.project_id.replace('proj_', '').slice(-6).toUpperCase();
}

function getHomeStatusLabel(project: Project): string {
  if (project.pending_decision) {
    return `${getDecisionGateLabel(project)} gate`;
  }

  return getStageLabel(project.current_stage);
}

function getHomeStatusHint(project: Project): string {
  if (project.pending_decision) {
    return '需要你决定是否继续推进';
  }

  if (project.status === 'completed') {
    return '提案已完成，可以进入阅读与复核';
  }

  if (project.status === 'failed') {
    return '研究链路出现异常，建议优先检查';
  }

  if (project.status === 'terminated') {
    return '项目已终止，保留历史记录';
  }

  return 'Agent 正在推进研究链路';
}

function getActivityHeadline(project: Project): string {
  if (project.pending_decision) {
    return `${project.brief.category} 等待 ${getDecisionGateLabel(project)} 审批`;
  }

  if (project.status === 'completed') {
    return `${project.brief.category} 已完成提案`;
  }

  if (project.status === 'failed') {
    return `${project.brief.category} 出现失败节点`;
  }

  if (project.status === 'terminated') {
    return `${project.brief.category} 已终止`;
  }

  return `${project.brief.category} 正在研究中`;
}

function getActivityBadge(project: Project): { label: string; tone: 'accent' | 'warning' | 'danger' | 'success' } | null {
  if (project.pending_decision) {
    return { label: '需要处理', tone: 'warning' };
  }

  if (project.status === 'completed') {
    return { label: '已完成', tone: 'success' };
  }

  if (project.status === 'failed' || project.status === 'terminated') {
    return { label: '已阻塞', tone: 'danger' };
  }

  return null;
}

function HomeSectionHeader({
  index,
  title,
  action,
}: {
  index: number;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="home-section__heading">
      <div className="home-section__heading-main">
        <span className="home-section__index">{index}</span>
        <h2 className="home-section__title">{title}</h2>
      </div>
      {action ? <div className="home-section__action">{action}</div> : null}
    </div>
  );
}

export function NextActionPanel({ projects }: { projects: Project[] }) {
  const sortedProjects = [...projects].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at));
  const priorityProject =
    sortedProjects.find((project) => project.pending_decision) ??
    sortedProjects.find((project) => ['researching', 'supplementing_research', 'generating_report'].includes(project.status)) ??
    sortedProjects[0];

  if (!priorityProject) {
    return (
      <section className="home-section home-section--primary">
        <HomeSectionHeader index={1} title="NEXT ACTION" />
        <div className="home-empty">
          <strong>还没有可处理的研究任务</strong>
          <p>点击左侧“新建研究”，先创建第一条研究项目。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-section home-section--primary">
      <HomeSectionHeader index={1} title="NEXT ACTION" />
      <div className="next-action-banner">
        <div className="next-action-banner__icon" aria-hidden="true">
          <svg fill="none" viewBox="0 0 20 20">
            <path
              d="M10 3.5L15.5 6.5V10.75C15.5 13.5 13.25 15.75 10 17C6.75 15.75 4.5 13.5 4.5 10.75V6.5L10 3.5Z"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.5"
            />
            <path d="M10 7.25V10.5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
            <circle cx="10" cy="13" r="0.8" fill="currentColor" />
          </svg>
        </div>
        <div className="next-action-banner__main">
          <div className="next-action-banner__badges">
            <Badge tone={getProjectBadgeTone(priorityProject.status)}>{STATUS_LABELS[priorityProject.status]}</Badge>
            {priorityProject.pending_decision ? <Badge tone="warning">{getDecisionGateLabel(priorityProject)} gate</Badge> : null}
          </div>
          <h3>{priorityProject.brief.category}</h3>
          <p>{getHomeStatusHint(priorityProject)}</p>
          <div className="next-action-banner__meta">
            <span>#{getProjectShortCode(priorityProject)}</span>
            <span>{priorityProject.brief.target_user}</span>
            <span>{formatDateTime(priorityProject.updated_at)}</span>
          </div>
        </div>
        <div className="next-action-banner__side">
          <div className="next-action-banner__stage">
            <strong>{getHomeStatusLabel(priorityProject)}</strong>
            <span>{priorityProject.pending_decision ? 'waiting for review' : `${priorityProject.progress}% complete`}</span>
          </div>
          <div className="next-action-banner__actions">
            <Link className="ui-button ui-button--primary" to={`/projects/${priorityProject.project_id}`}>
              立即处理
            </Link>
            <Link className="ui-button ui-button--ghost" to={`/projects/${priorityProject.project_id}`}>
              查看项目
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ContinueWorkingPanel({ projects }: { projects: Project[] }) {
  const items = [...projects].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)).slice(0, 4);

  return (
    <section className="home-section">
      <HomeSectionHeader
        index={2}
        title="CONTINUE WORKING"
        action={
          items[0] ? (
            <Link className="home-section__link" to={`/projects/${items[0].project_id}`}>
              查看项目
            </Link>
          ) : null
        }
      />
      {items.length === 0 ? (
        <div className="home-empty">
          <strong>暂无项目</strong>
          <p>创建研究后，这里会保留最近的工作入口。</p>
        </div>
      ) : (
        <div className="home-work-list">
          {items.map((project) => (
            <Link className="home-work-list__item" key={project.project_id} to={`/projects/${project.project_id}`}>
              <div className={`home-work-list__marker home-work-list__marker--${getProjectBadgeTone(project.status)}`} aria-hidden="true">
                <span>{project.brief.category.slice(0, 1).toUpperCase()}</span>
              </div>
              <div className="home-work-list__main">
                <div className="home-work-list__header">
                  <strong>{project.brief.category}</strong>
                  <Badge tone={getProjectBadgeTone(project.status)}>{STATUS_LABELS[project.status]}</Badge>
                </div>
                <div className="home-work-list__subline">
                  <span>#{getProjectShortCode(project)}</span>
                  <span>{project.brief.target_user}</span>
                </div>
              </div>
              <div className="home-work-list__progress">
                <div className="home-work-list__progress-head">
                  <strong>{getHomeStatusLabel(project)}</strong>
                  <span>{project.pending_decision ? 'manual gate' : `${project.progress}%`}</span>
                </div>
                <div className="home-work-list__progress-bar" aria-hidden="true">
                  <span style={{ width: `${project.pending_decision ? 100 : project.progress}%` }} />
                </div>
              </div>
              <div className="home-work-list__meta">
                <span>{formatDateTime(project.updated_at)}</span>
                <span className="home-work-list__chevron" aria-hidden="true">
                  <svg fill="none" viewBox="0 0 16 16">
                    <path d="M6 3.5L10 8L6 12.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
                  </svg>
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export function ProjectActivityRail({ projects }: { projects: Project[] }) {
  const items = [...projects]
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))
    .slice(0, 5);

  if (items.length === 0) {
    return (
      <section className="home-section">
        <HomeSectionHeader index={3} title="RECENT ACTIVITY" />
        <div className="home-empty">
          <strong>还没有最近动态</strong>
          <p>创建项目后，这里会开始汇总研究推进和人工 gate。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-section">
      <HomeSectionHeader index={3} title="RECENT ACTIVITY" />
      <div className="home-activity-list">
        {items.map((project) => {
          const badge = getActivityBadge(project);

          return (
            <Link className="home-activity-list__item" key={project.project_id} to={`/projects/${project.project_id}`}>
              <div className={`home-activity-list__dot home-activity-list__dot--${getProjectBadgeTone(project.status)}`} aria-hidden="true" />
              <div className="home-activity-list__main">
                <strong>{getActivityHeadline(project)}</strong>
                <p>{getHomeStatusLabel(project)}</p>
              </div>
              <div className="home-activity-list__meta">
                <span>{formatDateTime(project.updated_at)}</span>
                {badge ? <Badge tone={badge.tone}>{badge.label}</Badge> : null}
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
