import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useDecisionMutation, useProjectEvents, useProjectsQuery, useResolvedView, useWorkspaceQuery } from '../shared/api/hooks';
import { formatDateTime } from '../shared/lib/format';
import { DECISION_COPY, EVENT_COPY, describeEvent, getDefaultViewForStatus, STATUS_LABELS, VIEW_LABELS } from '../shared/lib/project';
import type { AgentRun, Claim, DecisionAction, Metrics, Project, ProjectEvent, ViewMode } from '../shared/types/api';
import { Badge, Button, EmptyState } from '../shared/ui/primitives';
import {
  BriefReviewPanel,
  ClaimEvidenceGraph,
  ConceptComparisonBoard,
  EvidenceListPanel,
  ReportEvidenceInspector,
} from '../widgets/app-shell/WorkbenchComponents';

const PROJECT_VIEW_ORDER: ViewMode[] = ['brief', 'live', 'concepts', 'proposal', 'evidence'];

type StageStep = {
  key: string;
  label: string;
  view: ViewMode;
};

const PROJECT_STAGE_STEPS: StageStep[] = [
  { key: 'brief', label: 'Brief 确认', view: 'brief' },
  { key: 'planning', label: '研究计划', view: 'live' },
  { key: 'concept', label: '概念晋级', view: 'concepts' },
  { key: 'proposal', label: '生成提案', view: 'proposal' },
  { key: 'final', label: '最终审批', view: 'proposal' },
  { key: 'done', label: '已完成', view: 'proposal' },
];

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

function getPendingTaskTitle(project: Project): string {
  if (project.pending_decision?.gate === 'brief') {
    return '当前需要你的 Brief 确认';
  }

  if (project.pending_decision?.gate === 'concept') {
    return '当前需要你的概念晋级决策';
  }

  if (project.pending_decision?.gate === 'final') {
    return '当前需要你的最终审批';
  }

  if (project.status === 'researching') {
    return '研究计划生成后需要你的确认';
  }

  if (project.status === 'supplementing_research') {
    return '当前链路仍在补证，建议关注空证据 Claim';
  }

  if (project.status === 'generating_report') {
    return '提案正在生成，建议关注引用证据完整性';
  }

  return '当前没有待审批事项';
}

function getPendingTaskMeta(project: Project): string {
  if (project.pending_decision) {
    return `更新于 ${formatDateTime(project.updated_at)}`;
  }

  if (project.status === 'researching') {
    return '预计完成：今日';
  }

  return `最近更新：${formatDateTime(project.updated_at)}`;
}

function getRiskItems(project: Project, claims: Claim[]): string[] {
  const items = ['最终结论必须能追溯到有效 Evidence IDs。'];

  if (claims.some((claim) => claim.evidence_ids.length === 0)) {
    items.push('存在缺少支持证据的 Claim，需要补证或显式降级。');
  } else {
    items.push('概念晋级前必须看见红队意见和空证据 Claim。');
  }

  if (project.status === 'failed') {
    items.unshift('当前项目存在失败节点，建议优先排查失败事件与恢复入口。');
  }

  return items.slice(0, 2);
}

function formatCoverage(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '0%';
  }

  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

function getMetricsRows(metrics: Metrics | null, claims: Claim[], fallbackEvidenceCount: number) {
  const validClaims = claims.filter((claim) => claim.evidence_ids.length > 0).length;
  const unresolvedClaims = claims.filter((claim) => claim.evidence_ids.length === 0).length;

  return [
    { label: 'Evidence', value: `${metrics?.valid_evidence_count ?? fallbackEvidenceCount}` },
    { label: '有效 Claim', value: `${validClaims}` },
    { label: '待验证结论', value: `${unresolvedClaims}` },
    { label: '研究覆盖率', value: formatCoverage(metrics?.citation_coverage) },
  ];
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

function getStageView(key: string): ViewMode {
  switch (key) {
    case 'brief':
      return 'brief';
    case 'planning':
      return 'live';
    case 'concept':
      return 'concepts';
    case 'proposal':
    case 'final':
    case 'done':
      return 'proposal';
    default:
      return 'live';
  }
}

function getSelectedStageKey(view: ViewMode): string {
  switch (view) {
    case 'brief':
      return 'brief';
    case 'live':
      return 'planning';
    case 'concepts':
      return 'concept';
    case 'proposal':
      return 'proposal';
    case 'evidence':
      return 'planning';
    default:
      return 'planning';
  }
}

function ProjectViewTabs({
  currentView,
  onChange,
}: {
  currentView: ViewMode;
  onChange: (view: ViewMode) => void;
}) {
  return (
    <nav className="project-workspace__tabs" aria-label="项目视图">
      {PROJECT_VIEW_ORDER.map((view) => (
        <button
          key={view}
          type="button"
          className={`project-workspace__tab${currentView === view ? ' project-workspace__tab--active' : ''}`}
          onClick={() => onChange(view)}
        >
          {VIEW_LABELS[view]}
        </button>
      ))}
    </nav>
  );
}

function ProjectStageRailPanel({
  currentView,
  onNavigate,
}: {
  currentView: ViewMode;
  onNavigate: (view: ViewMode) => void;
}) {
  const selectedStageKey = getSelectedStageKey(currentView);

  return (
    <section className="project-workspace__panel project-workspace__panel--stage">
      <h3 className="project-workspace__panel-title">研究流转</h3>
      <div className="project-workspace__stage-list">
        {PROJECT_STAGE_STEPS.map((step) => {
          const selected = step.key === selectedStageKey;

          return (
            <button
              type="button"
              className={`project-workspace__stage-item${selected ? ' project-workspace__stage-item--selected' : ''}`}
              key={step.key}
              onClick={() => onNavigate(getStageView(step.key))}
            >
              <span className="project-workspace__stage-dot" aria-hidden="true" />
              <div className="project-workspace__stage-copy">
                <strong>{step.label}</strong>
                <span>{selected ? '当前查看' : '点击查看'}</span>
              </div>
              {selected ? (
                <span className="project-workspace__stage-arrow" aria-hidden="true">
                  <svg fill="none" viewBox="0 0 16 16">
                    <path d="M6 3.5L10 8L6 12.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
                  </svg>
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function LiveResearchOverview({
  project,
  onPrimaryAction,
}: {
  project: Project;
  onPrimaryAction?: (() => void) | null;
}) {
  const primaryLabel = project.pending_decision ? DECISION_COPY[project.pending_decision.allowed_actions[0]].label : '继续推进研究';

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
  return (
    <section className="project-workspace__panel" id="project-agent-status">
      <h3 className="project-workspace__panel-title">Agent 运行状态</h3>
      <div className="project-workspace__agent-list">
        {agentRuns.length === 0 ? (
          <div className="project-workspace__empty-inline">
            <strong>当前还没有活跃 Agent</strong>
            <p>系统一旦开始执行研究任务，这里会显示运行态、进度和等待节点。</p>
          </div>
        ) : (
          agentRuns.map((agent) => (
            <article className="project-workspace__agent-row" key={agent.agent_run_id}>
              <div className={`project-workspace__agent-avatar project-workspace__agent-avatar--${getAgentMarkerTone(agent.status)}`}>
                <span>{getAgentInitial(agent.agent_name)}</span>
              </div>
              <div className="project-workspace__agent-main">
                <strong>{agent.agent_name}</strong>
                <p>{agent.message}</p>
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

function ProjectTaskPanel({
  project,
  busy,
  onDecision,
}: {
  project: Project;
  busy: boolean;
  onDecision: (action: DecisionAction) => void;
}) {
  const hasPendingDecision = Boolean(project.pending_decision);
  const actionCount = hasPendingDecision ? project.pending_decision!.allowed_actions.length : 1;

  return (
    <section className="project-workspace__panel">
      <div className="project-workspace__side-head">
        <h3 className="project-workspace__panel-title">待处理事项</h3>
        <span className="project-workspace__count-badge">{actionCount}</span>
      </div>
      <div className="project-workspace__task-card">
        <div className="project-workspace__task-icon" aria-hidden="true">
          <svg fill="none" viewBox="0 0 20 20">
            <path d="M10 5.25V10L13 12.25" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
            <circle cx="10" cy="10" r="6.25" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </div>
        <div className="project-workspace__task-copy">
          <strong>{getPendingTaskTitle(project)}</strong>
          <p>{getPendingTaskMeta(project)}</p>
        </div>
        {project.pending_decision ? (
          <div className="project-workspace__task-actions">
            {project.pending_decision.allowed_actions.slice(0, 2).map((action) => (
              <Button
                key={action}
                tone={DECISION_COPY[action].tone}
                disabled={busy}
                onClick={() => onDecision(action)}
              >
                {DECISION_COPY[action].label}
              </Button>
            ))}
          </div>
        ) : (
          <Link className="project-workspace__task-link" to={`/projects/${project.project_id}/metrics`}>
            查看详情
          </Link>
        )}
      </div>
    </section>
  );
}

function ProjectRiskPanel({ project, claims }: { project: Project; claims: Claim[] }) {
  const items = getRiskItems(project, claims);

  return (
    <section className="project-workspace__panel">
      <h3 className="project-workspace__panel-title">风险提醒</h3>
      <div className="project-workspace__risk-list">
        {items.map((item) => (
          <article className="project-workspace__risk-item" key={item}>
            <span className="project-workspace__risk-icon" aria-hidden="true">
              <svg fill="none" viewBox="0 0 20 20">
                <path d="M10 4.25L16 15.25H4L10 4.25Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.5" />
                <path d="M10 8V11.25" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
                <circle cx="10" cy="13.5" r="0.85" fill="currentColor" />
              </svg>
            </span>
            <p>{item}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function ProjectMetricsPanel({
  metrics,
  claims,
  evidenceCount,
}: {
  metrics: Metrics | null;
  claims: Claim[];
  evidenceCount: number;
}) {
  const rows = getMetricsRows(metrics, claims, evidenceCount);

  return (
    <section className="project-workspace__panel">
      <h3 className="project-workspace__panel-title">指标速览</h3>
      <div className="project-workspace__metric-list">
        {rows.map((row) => (
          <div className="project-workspace__metric-row" key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ProjectWorkbenchPage() {
  const params = useParams();
  const projectId = params.projectId ?? '';
  const workspaceQuery = useWorkspaceQuery(projectId);
  const projectsQuery = useProjectsQuery();
  const decisionMutation = useDecisionMutation(projectId);
  const [selectedView, setSelectedView] = useState<ViewMode | null>(null);

  const fallbackProject = projectsQuery.data?.find((item) => item.project_id === projectId);
  const placeholderProject = projectId ? buildPlaceholderProject(projectId) : undefined;
  const project = workspaceQuery.data?.project ?? fallbackProject ?? placeholderProject;

  useEffect(() => {
    if (project) {
      setSelectedView((current) => current ?? getDefaultViewForStatus(project.status));
    }
  }, [project]);

  const activeView = useResolvedView(project, selectedView);
  const fallbackEvents = project ? buildFallbackEvents(project) : [];
  const { events } = useProjectEvents(projectId, workspaceQuery.data?.events ?? fallbackEvents);

  if (!projectId) {
    return (
      <main className="screen">
        <EmptyState title="项目不存在" description="请返回项目列表重新选择。" />
      </main>
    );
  }

  const activeProject = project ?? buildPlaceholderProject(projectId);
  const agentRuns = workspaceQuery.data?.agentRuns ?? buildFallbackAgentRuns(activeProject);
  const evidencePage = workspaceQuery.data?.evidencePage ?? { items: [], next_cursor: null, total: 0 };
  const claims = workspaceQuery.data?.claims ?? [];
  const concepts = workspaceQuery.data?.concepts ?? [];
  const report = workspaceQuery.data?.report ?? null;
  const metrics = workspaceQuery.data?.metrics ?? null;

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

  return (
    <main className="workspace-screen workspace-screen--project-detail">
      <header className="project-workspace__hero">
        <div className="project-workspace__hero-main">
          <p className="project-workspace__eyebrow">Project Workspace</p>
          <h1 className="project-workspace__title">{activeProject.brief.category}</h1>
          <div className="project-workspace__summary">
            <span>{activeProject.brief.target_user}</span>
            <Badge tone={getProjectBadgeTone(activeProject.status)}>{STATUS_LABELS[activeProject.status]}</Badge>
            <span>{activeProject.progress}%</span>
            <div className="project-workspace__summary-progress" aria-hidden="true">
              <span style={{ width: `${activeProject.progress}%` }} />
            </div>
            <span>更新于</span>
            <strong>{formatDateTime(activeProject.updated_at)}</strong>
          </div>
        </div>
        <div className="project-workspace__hero-actions">
          <Link className="ui-button ui-button--ghost" to={`/projects/${activeProject.project_id}/metrics`}>
            查看指标
          </Link>
          <Link className="ui-button ui-button--primary" to={`/projects/${activeProject.project_id}/report`}>
            打开提案页
          </Link>
        </div>
      </header>

      <ProjectViewTabs currentView={activeView} onChange={setSelectedView} />

      <div className="project-workspace__layout">
        <aside className="project-workspace__left">
          <ProjectStageRailPanel currentView={activeView} onNavigate={setSelectedView} />
        </aside>

        <section className="project-workspace__main">
          {activeView === 'live' ? (
            <>
              <LiveResearchOverview
                project={activeProject}
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
              <EvidenceListPanel evidence={evidencePage.items} claims={claims} />
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

        <aside className="project-workspace__right">
          <ProjectTaskPanel project={activeProject} busy={decisionMutation.isPending} onDecision={handleQuickDecision} />
          <ProjectRiskPanel project={activeProject} claims={claims} />
          <ProjectMetricsPanel metrics={metrics} claims={claims} evidenceCount={evidencePage.items.length} />
        </aside>
      </div>
    </main>
  );
}
