import { useEffect, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';

import { api } from '../shared/api/client';
import { useDecisionMutation, useProjectEvents, useProjectsQuery, useResolvedView, useWorkspaceQuery } from '../shared/api/hooks';
import { formatDateTime } from '../shared/lib/format';
import { DECISION_COPY, EVENT_COPY, describeEvent, getDefaultViewForStatus, STATUS_LABELS, VIEW_LABELS } from '../shared/lib/project';
import type { AgentRun, DecisionAction, Project, ProjectEvent, ViewMode } from '../shared/types/api';
import { Badge, Button, EmptyState } from '../shared/ui/primitives';
import {
  BriefReviewPanel,
  ClaimEvidenceGraph,
  ConceptComparisonBoard,
  EvidenceListPanel,
  ReportEvidenceInspector,
} from '../widgets/app-shell/WorkbenchComponents';

const PROJECT_VIEW_ORDER: ViewMode[] = ['brief', 'live', 'concepts', 'proposal', 'evidence'];

function getLatestWorkspaceTimestamp(project: Project, agentRuns: AgentRun[], events: ProjectEvent[]): string {
  const timestamps = [
    project.updated_at,
    ...agentRuns.flatMap((run) => [run.started_at, run.completed_at]),
    ...events.map((event) => event.timestamp),
  ].filter((value): value is string => Boolean(value));

  return timestamps.reduce((latest, candidate) => {
    const normalize = (value: string) => /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim()) ? value : `${value}Z`;
    return Date.parse(normalize(candidate)) > Date.parse(normalize(latest)) ? candidate : latest;
  }, project.updated_at);
}

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

function getStageHeading(project: Project): string {
  switch (project.status) {
    case 'awaiting_brief_approval':
      return 'Brief 确认阶段';
    case 'researching':
      return '研究计划阶段';
    case 'supplementing_research':
      return '补充研究阶段';
    case 'awaiting_concept_approval':
      return '概念晋级阶段';
    case 'generating_report':
      return '提案生成阶段';
    case 'awaiting_final_approval':
      return '最终审批阶段';
    case 'completed':
      return '项目完成阶段';
    case 'failed':
      return '异常恢复阶段';
    case 'terminated':
      return '项目终止阶段';
    default:
      return '研究执行阶段';
  }
}

function getStageDescription(project: Project): string {
  switch (project.status) {
    case 'awaiting_brief_approval':
      return 'Brief 已生成，等待你确认研究范围与约束后继续推进。';
    case 'researching':
      return 'Brief 已通过，系统正在生成调研任务和研究计划。';
    case 'supplementing_research':
      return '已有研究链路正在补证，系统正在继续扩展关键证据覆盖。';
    case 'awaiting_concept_approval':
      return '研究已完成初步收敛，系统正在等待概念晋级决策。';
    case 'generating_report':
      return '概念已确认，系统正在整理 recommendation 与 cited evidence。';
    case 'awaiting_final_approval':
      return '提案已生成，当前等待最终审批决定是否完成项目。';
    case 'completed':
      return '项目已完成，当前建议可以进入阅读、复核与归档。';
    case 'failed':
      return '研究链路出现异常，当前需要优先确认失败节点与恢复方式。';
    case 'terminated':
      return '项目已终止，保留当前链路记录供后续复盘与参考。';
    default:
      return '系统正在推进当前研究阶段。';
  }
}

function getStageGoal(project: Project): string {
  switch (project.status) {
    case 'awaiting_brief_approval':
      return '确认核心问题、目标用户与关键约束是否可以进入正式研究。';
    case 'researching':
      return '完成用户、市场及竞品研究计划拆分。';
    case 'supplementing_research':
      return '补齐关键 Claim 的证据缺口与冲突来源。';
    case 'awaiting_concept_approval':
      return '确认哪个概念值得进入提案阶段。';
    case 'generating_report':
      return '完成 recommendation、citations 与 unknowns 整理。';
    case 'awaiting_final_approval':
      return '确认最终建议是否可以批准并进入完成态。';
    case 'completed':
      return '复核引用证据、限制条件和最终输出质量。';
    case 'failed':
      return '定位失败原因并判断是否需要补充研究或终止。';
    case 'terminated':
      return '保留研究记录并输出终止原因。';
    default:
      return '推进当前阶段。';
  }
}

function getAgentStatusLabel(status: AgentRun['status']): string {
  switch (status) {
    case 'running':
      return 'Running';
    case 'waiting':
      return 'Waiting';
    case 'queued':
      return 'Queued';
    case 'completed':
      return 'Done';
    case 'failed':
      return 'Failed';
    case 'cancelled':
      return 'Stopped';
    default:
      return status;
  }
}

function getAgentStatusTone(status: AgentRun['status']): 'accent' | 'warning' | 'danger' | 'success' | 'neutral' {
  switch (status) {
    case 'running':
      return 'accent';
    case 'waiting':
    case 'queued':
      return 'neutral';
    case 'completed':
      return 'success';
    case 'failed':
    case 'cancelled':
      return 'danger';
    default:
      return 'neutral';
  }
}

function getAgentMarkerTone(status: AgentRun['status']): 'accent' | 'warning' | 'danger' | 'success' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
    case 'cancelled':
      return 'danger';
    case 'waiting':
    case 'queued':
      return 'warning';
    default:
      return 'accent';
  }
}

function getAgentInitial(name: string): string {
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : 'A';
}

function AgentStatusIcon({ status, name }: { status: AgentRun['status']; name: string }) {
  if (status === 'running') {
    return (
      <svg
        className="project-workspace__agent-refresh-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-label={`${name} 正在运行`}
      >
        <path d="M20 11a8.1 8.1 0 0 0-14.8-4L3 10" />
        <path d="M3 4v6h6" />
        <path d="M4 13a8.1 8.1 0 0 0 14.8 4L21 14" />
        <path d="M21 20v-6h-6" />
      </svg>
    );
  }

  return <span>{getAgentInitial(name)}</span>;
}

function getLatestAgentRuns(runs: AgentRun[]): Array<{ agent: AgentRun; attempts: number }> {
  const grouped = new Map<string, AgentRun[]>();
  for (const run of runs) {
    const history = grouped.get(run.agent_type) ?? [];
    history.push(run);
    grouped.set(run.agent_type, history);
  }

  return Array.from(grouped.values()).map((history) => {
    history.sort((left, right) => {
      const leftTime = Date.parse(left.started_at ?? left.completed_at ?? '') || 0;
      const rightTime = Date.parse(right.started_at ?? right.completed_at ?? '') || 0;
      return rightTime - leftTime;
    });
    return { agent: history[0], attempts: history.length };
  });
}

function buildPlaceholderProject(projectId: string): Project {
  const now = new Date().toISOString();

  return {
    project_id: projectId,
    status: 'researching',
    current_stage: 'research_planning',
    progress: 10,
    brief: {
      question: 'eufy 是否应该为北美租房用户设计一套低安装门槛、可迁移、低订阅依赖的家庭安防方案？',
      category: '家庭安防',
      target_user: '北美租房家庭与合租用户',
      region: '美国 / 加拿大',
      scenarios: ['门口访客', '搬家迁移'],
      constraints: ['免打孔', '低订阅依赖'],
      focus_dimensions: ['安装', '迁移'],
    },
    pending_decision: null,
    created_at: now,
    updated_at: now,
  };
}

function buildFallbackAgentRuns(project: Project): AgentRun[] {
  const runningStatus = project.status === 'researching' || project.status === 'supplementing_research' || project.status === 'generating_report';
  const waitingGate = Boolean(project.pending_decision);

  return [
    {
      agent_run_id: `${project.project_id}_manager`,
      project_id: project.project_id,
      agent_type: 'manager',
      agent_name: '调研总管 Agent',
      status: runningStatus ? 'running' : waitingGate ? 'waiting' : 'queued',
      progress: Math.max(18, project.progress),
      message: runningStatus ? '正在规划并推进研究任务。' : waitingGate ? '等待当前 gate 决策后继续推进。' : '等待开始执行。',
      started_at: project.updated_at,
      completed_at: null,
    },
    {
      agent_run_id: `${project.project_id}_user`,
      project_id: project.project_id,
      agent_type: 'user_research',
      agent_name: '用户研究员',
      status: runningStatus ? 'waiting' : 'queued',
      progress: 0,
      message: '等待任务分配',
      started_at: null,
      completed_at: null,
    },
    {
      agent_run_id: `${project.project_id}_competitor`,
      project_id: project.project_id,
      agent_type: 'competitor',
      agent_name: '竞品研究员',
      status: runningStatus ? 'waiting' : 'queued',
      progress: 0,
      message: '等待任务分配',
      started_at: null,
      completed_at: null,
    },
    {
      agent_run_id: `${project.project_id}_evidence`,
      project_id: project.project_id,
      agent_type: 'evidence',
      agent_name: '证据审核员',
      status: 'queued',
      progress: 0,
      message: '未开始',
      started_at: null,
      completed_at: null,
    },
  ];
}

function buildFallbackEvents(project: Project): ProjectEvent[] {
  return [
    {
      event_id: `${project.project_id}_evt_1`,
      event_type: 'project_created',
      project_id: project.project_id,
      sequence_number: 1,
      timestamp: project.created_at,
      data: {},
      trace_id: `${project.project_id}_trace_1`,
    },
    {
      event_id: `${project.project_id}_evt_2`,
      event_type: project.pending_decision ? 'decision_requested' : 'research_started',
      project_id: project.project_id,
      sequence_number: 2,
      timestamp: project.updated_at,
      data: {},
      trace_id: `${project.project_id}_trace_2`,
    },
  ];
}

// These builders remain available for the explicitly opt-in demo mode only.
void buildPlaceholderProject;
void buildFallbackAgentRuns;
void buildFallbackEvents;

function getActivityTone(eventType: string): 'accent' | 'warning' | 'danger' | 'success' {
  const preset = EVENT_COPY[eventType];
  switch (preset?.tone) {
    case 'warning':
      return 'warning';
    case 'danger':
      return 'danger';
    case 'neutral':
      return 'accent';
    default:
      return preset?.tone ?? 'accent';
  }
}

function ProjectViewTabs({
  project,
  currentView,
  onChange,
}: {
  project: Project;
  currentView: ViewMode;
  onChange: (view: ViewMode) => void;
}) {
  const stageOrder: ViewMode[] = ['brief', 'live', 'evidence', 'concepts', 'proposal'];
  const currentStage = project.status === 'awaiting_concept_approval'
    ? 'concepts'
    : project.status === 'generating_report' || project.status === 'awaiting_final_approval' || project.status === 'completed'
      ? 'proposal'
      : project.status === 'researching' || project.status === 'supplementing_research' || project.status === 'failed'
        ? 'live'
        : 'brief';
  const currentStageIndex = stageOrder.indexOf(currentStage);

  return (
    <nav className="project-workspace__tabs" aria-label="项目视图">
      {PROJECT_VIEW_ORDER.map((view) => (
        (() => {
          const viewIndex = stageOrder.indexOf(view);
          const stageStatus = view === currentStage
            ? project.status === 'awaiting_final_approval' ? '最终审批' : project.status === 'completed' ? '已完成' : '当前阶段'
            : viewIndex < currentStageIndex ? '已完成' : '待进入';
          return (
            <button
              key={view}
              type="button"
              className={`project-workspace__tab${currentView === view ? ' project-workspace__tab--active' : ''}`}
              onClick={() => onChange(view)}
              aria-label={`${VIEW_LABELS[view]}，${stageStatus}`}
            >
              <span className="project-workspace__tab-label">{VIEW_LABELS[view]}</span>
              <span
                className={`project-workspace__tab-status project-workspace__tab-status--${stageStatus === '当前阶段' || stageStatus === '最终审批' ? 'current' : stageStatus === '已完成' ? 'done' : 'upcoming'}`}
                title={stageStatus}
                aria-hidden="true"
              >
                <span className="project-workspace__tab-status-dot" />
              </span>
            </button>
          );
        })()
      ))}
    </nav>
  );
}

function InlineEvidenceRecovery({ projectId, evidenceCount }: { projectId: string; evidenceCount: number }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [excerpt, setExcerpt] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.ingestEvidence(projectId, {
        source_url: sourceUrl,
        source_type: 'user_reviews',
        title,
        original_excerpt: excerpt,
        claim_type: 'user_opinion',
        status: 'partially_verified',
        collected_at: new Date().toISOString(),
        confidence: 0.7,
        authority_score: 0.7,
        recency_score: 0.8,
        diversity_score: 0.7,
      });
      await api.retryInitialResearch(projectId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workspace', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
      ]);
      setTitle('');
      setSourceUrl('');
      setExcerpt('');
      setOpen(false);
    } catch {
      setError('保存失败，请检查来源链接或后端服务。');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="inline-evidence-recovery">
      <div className="inline-evidence-recovery__copy">
        <strong>用户研究需要补充证据</strong>
        <span>当前已有 {evidenceCount} 条证据，建议补充来自不同来源的真实用户评论。</span>
      </div>
      <Button tone="primary" onClick={() => setOpen((current) => !current)}>{open ? '收起补充表单' : '补充证据并继续'}</Button>
      {open ? (
        <form className="inline-evidence-recovery__form" onSubmit={handleSubmit}>
          <label className="ui-field"><span>评论标题</span><input className="ui-input" required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：用户对夜间误报的反馈" /></label>
          <label className="ui-field"><span>来源链接</span><input className="ui-input" required type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." /></label>
          <label className="ui-field"><span>评论或访谈原文</span><textarea className="ui-textarea" required value={excerpt} onChange={(event) => setExcerpt(event.target.value)} placeholder="粘贴真实用户评论或访谈片段" /></label>
          <p className="muted-copy">保存后会自动重新运行 User Research Agent，无需跳转证据中心。</p>
          {error ? <p className="form-error">{error}</p> : null}
          <Button type="submit" disabled={submitting}>{submitting ? '保存并重试中…' : '保存并继续研究'}</Button>
        </form>
      ) : null}
    </div>
  );
}

function LiveResearchOverview({
  project,
  agentRuns,
  evidenceCount,
  onPrimaryAction,
}: {
  project: Project;
  agentRuns: AgentRun[];
  evidenceCount: number;
  onPrimaryAction?: (() => void) | null;
}) {
  const primaryLabel = project.pending_decision ? DECISION_COPY[project.pending_decision.allowed_actions[0]].label : '查看 Agent 进度';

  return (
    <section className="project-workspace__panel project-workspace__stage-summary" id="project-stage-summary">
      <div className="project-workspace__stage-summary-head">
        <h3 className="project-workspace__panel-title">{getStageHeading(project)}</h3>
        <span className="project-workspace__stage-percent">{project.progress}%</span>
      </div>
      <p className="project-workspace__panel-copy">{getStageDescription(project)}</p>
      <div className="project-workspace__goal-block">
        <strong>当前目标</strong>
        <p>{getStageGoal(project)}</p>
      </div>
      {project.status === 'researching' && agentRuns.some((run) => run.status === 'blocked' || run.status === 'partial') ? (
        <InlineEvidenceRecovery projectId={project.project_id} evidenceCount={evidenceCount} />
      ) : null}
      <div className="project-workspace__stage-actions">
        {project.pending_decision && onPrimaryAction ? (
          <Button tone={DECISION_COPY[project.pending_decision.allowed_actions[0]].tone} onClick={onPrimaryAction}>
            {primaryLabel}
          </Button>
        ) : (
          <a className="ui-button ui-button--primary" href="#project-agent-status">
            {primaryLabel}
          </a>
        )}
        <a className="ui-button ui-button--ghost" href="#project-recent-activity">
          查看研究计划
        </a>
      </div>
    </section>
  );
}

function LiveAgentStatusPanel({ agentRuns }: { agentRuns: AgentRun[] }) {
  const latestRuns = getLatestAgentRuns(agentRuns);
  return (
    <section className="project-workspace__panel" id="project-agent-status">
      <h3 className="project-workspace__panel-title">Agent 运行状态</h3>
      <div className="project-workspace__agent-list">
        {latestRuns.length === 0 ? (
          <div className="project-workspace__empty-inline">
            <strong>当前还没有活跃 Agent</strong>
            <p>系统一旦开始执行研究任务，这里会显示运行态、进度和等待节点。</p>
          </div>
        ) : (
          latestRuns.map(({ agent, attempts }) => (
            <article className="project-workspace__agent-row" key={agent.agent_type}>
              <div className={`project-workspace__agent-avatar project-workspace__agent-avatar--${getAgentMarkerTone(agent.status)}`}>
                <AgentStatusIcon status={agent.status} name={agent.agent_name} />
              </div>
              <div className="project-workspace__agent-main">
                <strong>{agent.agent_name}</strong>
                <p>{agent.message}{attempts > 1 ? `（历史运行 ${attempts} 次，当前显示最新一次）` : ''}</p>
              </div>
              <div className="project-workspace__agent-state">
                <Badge tone={getAgentStatusTone(agent.status)}>{getAgentStatusLabel(agent.status)}</Badge>
                <span>{agent.progress}%</span>
              </div>
              <div className="project-workspace__agent-progress" aria-hidden="true">
                <span style={{ width: `${agent.progress}%` }} />
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function LiveRecentActivityPanel({ events }: { events: ProjectEvent[] }) {
  const items = [...events].sort((left, right) => right.sequence_number - left.sequence_number).slice(0, 4);

  return (
    <section className="project-workspace__panel" id="project-recent-activity">
      <h3 className="project-workspace__panel-title">最近活动</h3>
      {items.length === 0 ? (
        <div className="project-workspace__empty-inline">
          <strong>还没有事件</strong>
          <p>项目创建后，阶段推进、证据采集与审批动作会出现在这里。</p>
        </div>
      ) : (
        <div className="project-workspace__activity-list">
          {items.map((event) => (
            <div className="project-workspace__activity-row" key={event.event_id}>
              <span className="project-workspace__activity-time">{formatDateTime(event.timestamp)}</span>
              <span className={`project-workspace__activity-dot project-workspace__activity-dot--${getActivityTone(event.event_type)}`} aria-hidden="true" />
              <div className="project-workspace__activity-main">
                <strong>{describeEvent(event)}</strong>
                <p>#{event.sequence_number}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function ProjectWorkbenchPage() {
  const params = useParams();
  const projectId = params.projectId ?? '';
  const workspaceQuery = useWorkspaceQuery(projectId);
  const projectsQuery = useProjectsQuery();
  const decisionMutation = useDecisionMutation(projectId);
  const queryClient = useQueryClient();
  const [selectedView, setSelectedView] = useState<ViewMode | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const fallbackProject = projectsQuery.data?.find((item) => item.project_id === projectId);
  const project = workspaceQuery.data?.project ?? fallbackProject;

  useEffect(() => {
    if (project) {
      setSelectedView((current) => current ?? getDefaultViewForStatus(project.status));
    }
  }, [project]);

  const activeView = useResolvedView(project, selectedView);
  const { events } = useProjectEvents(projectId, workspaceQuery.data?.events ?? []);

  if (!projectId) {
    return (
      <main className="screen">
        <EmptyState title="项目不存在" description="请返回项目列表重新选择。" />
      </main>
    );
  }

  if (workspaceQuery.isLoading || projectsQuery.isLoading) {
    return <main className="screen"><EmptyState title="正在连接真实后端" description="正在读取项目、Agent、Evidence 和实时事件。" /></main>;
  }

  if (workspaceQuery.isError || !project) {
    return <main className="screen"><EmptyState title="无法读取项目数据" description="后端接口不可用或项目不存在，请检查服务状态后重试。" /></main>;
  }

  const activeProject = project;
  const agentRuns = workspaceQuery.data?.agentRuns ?? [];
  const latestAgentRuns = getLatestAgentRuns(agentRuns).map(({ agent }) => agent);
  const evidencePage = workspaceQuery.data?.evidencePage ?? { items: [], next_cursor: null, total: 0 };
  const claims = workspaceQuery.data?.claims ?? [];
  const concepts = workspaceQuery.data?.concepts ?? [];
  const report = workspaceQuery.data?.report ?? null;

  async function handleDecision(action: DecisionAction, reason: string): Promise<void> {
    if (!project?.pending_decision) {
      return;
    }

    const selectedConceptIds =
      action === 'approve' ? concepts.filter((concept) => concept.status !== 'rejected').slice(0, 1).map((concept) => concept.concept_id) : [];

    const updatedProject = await decisionMutation.mutateAsync({
      decisionId: project.pending_decision.decision_id,
      action,
      reason,
      selectedConceptIds,
    });
    setSelectedView(getDefaultViewForStatus(updatedProject.status));
  }

  function handleQuickDecision(action: DecisionAction): void {
    const fallbackReason = `Workspace quick action: ${DECISION_COPY[action].label}`;
    void handleDecision(action, fallbackReason);
  }

  async function handleRetryResearch(): Promise<void> {
    setRetrying(true);
    setRetryError(null);
    try {
      await api.retryInitialResearch(activeProject.project_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workspace', activeProject.project_id] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
      ]);
      setSelectedView('live');
    } catch {
      setRetryError('重试启动失败，请检查后端服务和 Provider 状态。');
    } finally {
      setRetrying(false);
    }
  }

  return (
    <main className="workspace-screen workspace-screen--project-detail">
      <header className="project-workspace__hero">
        <div className="project-workspace__hero-main">
          <p className="project-workspace__eyebrow">Project Workspace</p>
          <h1 className="project-workspace__title">{activeProject.brief.category}</h1>
          <div className="project-workspace__summary">
            <Badge tone={getProjectBadgeTone(activeProject.status)}>{STATUS_LABELS[activeProject.status]}</Badge>
            <span className="project-workspace__summary-progress-label">{activeProject.progress}%</span>
            <div className="project-workspace__summary-progress" aria-hidden="true">
              <span style={{ width: `${activeProject.progress}%` }} />
            </div>
            <span className="project-workspace__summary-updated">更新于 {formatDateTime(getLatestWorkspaceTimestamp(activeProject, agentRuns, events))}</span>
          </div>
        </div>
        <div className="project-workspace__hero-actions">
          {activeProject.pending_decision ? (
            <>
              <Button
                tone={DECISION_COPY[activeProject.pending_decision.allowed_actions[0]].tone}
                disabled={decisionMutation.isPending}
                onClick={() => handleQuickDecision(activeProject.pending_decision!.allowed_actions[0])}
              >
                {DECISION_COPY[activeProject.pending_decision.allowed_actions[0]].label}
              </Button>
              <Link className="ui-button ui-button--ghost" to={`/projects/${activeProject.project_id}/metrics`}>
                查看指标
              </Link>
            </>
          ) : activeProject.status === 'failed' ? (
            <>
              <a className="ui-button ui-button--ghost" href="#project-agent-status">
                查看失败原因
              </a>
              <Button tone="primary" disabled={retrying} onClick={() => { void handleRetryResearch(); }}>
                {retrying ? '重试启动中…' : '重试研究'}
              </Button>
            </>
          ) : (
            <>
              <Link className="ui-button ui-button--ghost" to={`/projects/${activeProject.project_id}/metrics`}>
                查看指标
              </Link>
              <Link className="ui-button ui-button--primary" to={`/projects/${activeProject.project_id}/report`}>
                打开提案页
              </Link>
            </>
          )}
          {retryError ? <span className="project-workspace__hero-error" role="alert">{retryError}</span> : null}
        </div>
      </header>

      <ProjectViewTabs project={activeProject} currentView={activeView} onChange={setSelectedView} />

      <div className="project-workspace__layout">
        <section className="project-workspace__main">
          {activeView === 'live' ? (
            <>
              <LiveResearchOverview
                project={activeProject}
                agentRuns={latestAgentRuns}
                evidenceCount={evidencePage.total}
                onPrimaryAction={
                  activeProject.pending_decision ? () => handleQuickDecision(activeProject.pending_decision!.allowed_actions[0]) : null
                }
              />
              <LiveAgentStatusPanel agentRuns={agentRuns} />
              <LiveRecentActivityPanel events={events} />
            </>
          ) : null}

          {activeView === 'brief' ? (
            <div className="project-workspace__content-stack">
              <BriefReviewPanel brief={activeProject.brief} status={activeProject.status} />
            </div>
          ) : null}

          {activeView === 'evidence' ? (
            <div className="project-workspace__content-stack">
              <EvidenceListPanel projectId={activeProject.project_id} evidence={evidencePage.items} claims={claims} />
              <ClaimEvidenceGraph claims={claims} />
            </div>
          ) : null}

          {activeView === 'concepts' ? (
            <div className="project-workspace__content-stack">
              <ConceptComparisonBoard concepts={concepts} />
            </div>
          ) : null}

          {activeView === 'proposal' ? (
            <div className="project-workspace__content-stack">
              <ReportEvidenceInspector report={report} claims={claims} />
            </div>
          ) : null}
        </section>

      </div>
    </main>
  );
}
