import type { DecisionAction, ProjectStatus, ProjectEvent, ViewMode } from '../types/api';

export const STAGE_ORDER: ProjectStatus[] = [
  'awaiting_brief_approval',
  'researching',
  'awaiting_concept_approval',
  'generating_report',
  'awaiting_final_approval',
  'completed',
];

export const STATUS_LABELS: Record<ProjectStatus, string> = {
  draft: '草稿',
  awaiting_brief_approval: '待确认 Brief',
  researching: '研究进行中',
  awaiting_concept_approval: '待概念晋级',
  supplementing_research: '补充调研中',
  generating_report: '生成提案中',
  awaiting_final_approval: '待最终审批',
  completed: '已完成',
  failed: '执行失败',
  terminated: '已终止',
};

export const VIEW_LABELS: Record<ViewMode, string> = {
  brief: 'Brief Review',
  live: 'Live Research',
  evidence: 'Evidence Center',
  concepts: 'Concept Arena',
  proposal: 'Proposal Review',
};

export const DECISION_COPY: Record<
  DecisionAction,
  { label: string; tone: 'primary' | 'ghost' | 'danger'; description: string }
> = {
  approve: { label: '批准', tone: 'primary', description: '继续进入下一阶段。' },
  revise: { label: '要求修订', tone: 'ghost', description: '退回修订当前提案。' },
  research_more: { label: '补充调研', tone: 'ghost', description: '要求继续补齐证据。' },
  reject: { label: '拒绝', tone: 'danger', description: '否决当前候选概念。' },
  terminate: { label: '终止', tone: 'danger', description: '终止该研究项目。' },
};

export const EVENT_COPY: Record<string, { label: string; tone: 'neutral' | 'accent' | 'warning' | 'danger' }> = {
  project_created: { label: '项目创建', tone: 'accent' },
  decision_requested: { label: '等待人工决策', tone: 'warning' },
  decision_submitted: { label: '已提交决策', tone: 'accent' },
  research_started: { label: '研究启动', tone: 'accent' },
  evidence_collected: { label: '证据入湖', tone: 'neutral' },
  evidence_failed: { label: '采集失败', tone: 'danger' },
  concept_generated: { label: '候选概念生成', tone: 'neutral' },
  report_generated: { label: '提案生成', tone: 'accent' },
};

export function getDefaultViewForStatus(status: ProjectStatus): ViewMode {
  switch (status) {
    case 'draft':
    case 'awaiting_brief_approval':
      return 'brief';
    case 'researching':
    case 'supplementing_research':
    case 'generating_report':
    case 'failed':
    case 'terminated':
      return 'live';
    case 'awaiting_concept_approval':
      return 'concepts';
    case 'awaiting_final_approval':
    case 'completed':
      return 'proposal';
    default:
      return 'live';
  }
}

export function describeEvent(event: ProjectEvent): string {
  const preset = EVENT_COPY[event.event_type];
  if (preset) {
    return preset.label;
  }

  return event.event_type.replaceAll('_', ' ');
}
