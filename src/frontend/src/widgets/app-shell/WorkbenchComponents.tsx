import type { FormEvent } from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '../../shared/api/client';
import { summarizeMetrics } from '../../shared/api/hooks';
import { formatCurrency, formatDateTime, formatPercent, titleCaseKey } from '../../shared/lib/format';
import {
  DECISION_COPY,
  EVENT_COPY,
  STATUS_LABELS,
  STAGE_ORDER,
  VIEW_LABELS,
  describeEvent,
} from '../../shared/lib/project';
import type {
  AgentRun,
  Claim,
  Concept,
  DecisionAction,
  Evidence,
  Metrics,
  PendingDecision,
  Project,
  ProjectEvent,
  Report,
  ResearchBrief,
  ViewMode,
} from '../../shared/types/api';
import { Badge, Button, Card, EmptyState, SectionHeading, Stat } from '../../shared/ui/primitives';

const EUFY_CATEGORY_GROUPS = [
  {
    label: 'Security',
    options: [
      '家庭安防',
      'PoE NVR 安防系统',
      '户外摄像头',
      '室内摄像头',
      '视频门铃',
      '智能门锁',
      'HomeBase',
      '智能灯光',
      '安防配件',
    ],
  },
  {
    label: 'Clean',
    options: ['清洁家电', '扫地机器人', '割草机器人', '智能体重秤', '清洁配件'],
  },
  {
    label: 'Mom & Baby',
    options: ['母婴护理', '吸奶器', '婴儿监视器', '智能袜', '智能显示屏'],
  },
] as const;

const REGION_OPTIONS = ['美国', '加拿大', '美国 / 加拿大', '北美', '欧洲', '英国', '澳大利亚', '全球'] as const;
const SCENARIO_OPTIONS = ['门口访客', '搬家迁移', '离家看护', '室友共享空间', '包裹投递', '夜间告警'] as const;
const CONSTRAINT_OPTIONS = ['免打孔', '低订阅依赖', '本地隐私优先', '弱网可用', '低硬件成本', '可快速迁移'] as const;
const FOCUS_DIMENSION_OPTIONS = ['安装', '迁移', '隐私', '成本', '证据留存', '竞品差异'] as const;

function findCategoryGroupLabel(category: string): string {
  return EUFY_CATEGORY_GROUPS.find((group) => group.options.some((option) => option === category))?.label ?? EUFY_CATEGORY_GROUPS[0].label;
}

function getCategoryOptions(groupLabel: string): readonly string[] {
  return EUFY_CATEGORY_GROUPS.find((group) => group.label === groupLabel)?.options ?? EUFY_CATEGORY_GROUPS[0].options;
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

function getDecisionGateLabel(project: Project): string {
  if (!project.pending_decision) {
    return '无';
  }

  if (project.pending_decision.gate === 'brief') {
    return 'Brief';
  }

  if (project.pending_decision.gate === 'concept') {
    return 'Concept';
  }

  if (project.pending_decision.gate === 'final') {
    return 'Final';
  }

  return project.pending_decision.gate;
}

function getProjectPriorityLine(project: Project): string {
  if (project.pending_decision) {
    return `等待 ${getDecisionGateLabel(project)} gate`;
  }

  if (project.status === 'researching' || project.status === 'supplementing_research' || project.status === 'generating_report') {
    return 'Agent 正在推进研究链路';
  }

  if (project.status === 'completed') {
    return '提案已完成，可直接复盘';
  }

  if (project.status === 'failed') {
    return '存在失败节点，建议优先查看';
  }

  if (project.status === 'terminated') {
    return '项目已终止，保留历史记录';
  }

  return '等待下一步操作';
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

function getActivityLine(project: Project): string {
  if (project.pending_decision?.gate === 'brief') {
    return '等待 Brief gate';
  }

  if (project.pending_decision?.gate === 'concept') {
    return '等待 Concept gate';
  }

  if (project.pending_decision?.gate === 'final') {
    return '等待 Final gate';
  }

  if (project.status === 'researching' || project.status === 'supplementing_research' || project.status === 'generating_report') {
    return 'Agent 正在推进研究链路';
  }

  if (project.status === 'completed') {
    return '提案已完成';
  }

  if (project.status === 'failed') {
    return '研究链路出现失败节点';
  }

  if (project.status === 'terminated') {
    return '项目已终止';
  }

  return '等待下一步动作';
}

function SelectField({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: string;
  options: readonly string[];
  onChange: (nextValue: string) => void;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handlePointerDown(event: MouseEvent): void {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    }

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  return (
    <div className="ui-selectbox" ref={rootRef}>
      <button
        aria-controls={listboxId}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        className={`ui-selectbox__trigger${open ? ' ui-selectbox__trigger--open' : ''}`}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setOpen(true);
          }
        }}
        type="button"
      >
        <span>{value}</span>
        <span aria-hidden="true" className="ui-selectbox__chevron">
          <svg fill="none" height="16" viewBox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 6.5L8 10.5L12 6.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
          </svg>
        </span>
      </button>

      {open ? (
        <div className="ui-selectbox__content" id={listboxId} role="listbox">
          {options.map((option) => {
            const selected = option === value;

            return (
              <button
                aria-selected={selected}
                className={`ui-selectbox__option${selected ? ' ui-selectbox__option--selected' : ''}`}
                key={option}
                onClick={() => {
                  onChange(option);
                  setOpen(false);
                }}
                role="option"
                type="button"
              >
                <span>{option}</span>
                {selected ? (
                  <span aria-hidden="true" className="ui-selectbox__check">
                    <svg fill="none" height="16" viewBox="0 0 16 16" width="16" xmlns="http://www.w3.org/2000/svg">
                      <path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
                    </svg>
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function summarizeMultiple(values: string[]): string {
  if (values.length === 0) {
    return '未选择';
  }

  if (values.length <= 2) {
    return values.join('、');
  }

  return `${values.slice(0, 2).join('、')} +${values.length - 2}`;
}

function MultiSelectPopover({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string[];
  options: readonly string[];
  onChange: (nextValue: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const dialogId = useId();

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handlePointerDown(event: MouseEvent): void {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    }

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  return (
    <div className="multi-select-field" ref={rootRef}>
      <button
        aria-controls={dialogId}
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`multi-select-field__trigger${open ? ' multi-select-field__trigger--open' : ''}`}
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span className="multi-select-field__summary">{summarizeMultiple(value)}</span>
        <span className="multi-select-field__meta">{value.length > 0 ? `${value.length} 已选` : label}</span>
      </button>

      {open ? (
        <div className="multi-select-field__content" id={dialogId} role="dialog">
          <div className="multi-select-field__header">
            <strong>{label}</strong>
            <span>{value.length} 已选</span>
          </div>
          <div className="multi-select-field__options">
            {options.map((option) => {
              const selected = value.includes(option);

              return (
                <button
                  className={`multi-select-field__option${selected ? ' multi-select-field__option--selected' : ''}`}
                  key={option}
                  onClick={() => {
                    onChange(selected ? value.filter((item) => item !== option) : [...value, option]);
                  }}
                  type="button"
                >
                  <span className={`multi-select-field__checkbox${selected ? ' multi-select-field__checkbox--selected' : ''}`}>
                    {selected ? '✓' : ''}
                  </span>
                  <span>{option}</span>
                </button>
              );
            })}
          </div>
          <div className="multi-select-field__footer">
            <button className="ui-button ui-button--ghost" onClick={() => onChange([])} type="button">
              清空
            </button>
            <button className="ui-button ui-button--primary" onClick={() => setOpen(false)} type="button">
              完成
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ProjectStageRail({ project }: { project: Project }) {
  const currentIndex = STAGE_ORDER.indexOf(project.status);

  return (
    <Card>
      <SectionHeading eyebrow="阶段轨道" title="研究流转" description={project.current_stage} />
      <div className="stage-rail">
        {STAGE_ORDER.map((status, index) => {
          const state = currentIndex === -1 ? 'upcoming' : index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'upcoming';
          return (
            <div className={`stage-rail__item stage-rail__item--${state}`} key={status}>
              <span className="stage-rail__dot" />
              <div>
                <strong>{STATUS_LABELS[status]}</strong>
                <span>{state === 'done' ? '已完成' : state === 'current' ? '当前阶段' : '未开始'}</span>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export function DecisionGateBanner({
  pendingDecision,
  busy,
  onSubmit,
}: {
  pendingDecision: PendingDecision | null;
  busy: boolean;
  onSubmit: (action: DecisionAction, reason: string, selectedConceptIds: string[]) => Promise<void> | void;
}) {
  const [reason, setReason] = useState('');

  if (!pendingDecision) {
    return null;
  }

  return (
    <Card className="decision-banner">
      <div className="decision-banner__header">
        <div>
          <p className="section-heading__eyebrow">Human Gate</p>
          <h3>待处理审批: {pendingDecision.gate}</h3>
          <p>只有允许动作会展示，所有决策都会写入项目轨迹。</p>
        </div>
        <Badge tone="warning">待决策</Badge>
      </div>
      <form
        className="decision-banner__form"
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
        }}
      >
        <textarea
          className="ui-textarea"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="写下决策理由，便于后续审计与复盘。"
        />
        <div className="decision-banner__actions">
          {pendingDecision.allowed_actions.map((action) => {
            const copy = DECISION_COPY[action];
            return (
              <Button
                key={action}
                tone={copy.tone}
                disabled={busy || reason.trim().length === 0}
                onClick={() => onSubmit(action, reason, [])}
              >
                {copy.label}
              </Button>
            );
          })}
        </div>
      </form>
    </Card>
  );
}

export function AgentRunBoard({ agentRuns }: { agentRuns: AgentRun[] }) {
  return (
    <Card>
      <SectionHeading eyebrow="Agent Board" title="协作运行态" description="看见谁在推进，谁在等待，谁出了问题。" />
      <div className="agent-board">
        {agentRuns.map((agent) => (
          <article className="agent-card" key={agent.agent_run_id}>
            <div className="agent-card__header">
              <div>
                <h3>{agent.agent_name}</h3>
                <p>{agent.agent_type}</p>
              </div>
              <Badge tone={agent.status === 'failed' ? 'danger' : agent.status === 'completed' ? 'success' : 'accent'}>
                {agent.status}
              </Badge>
            </div>
            <div className="progress">
              <span style={{ width: `${agent.progress}%` }} />
            </div>
            <p className="agent-card__message">{agent.message}</p>
            <div className="agent-card__meta">
              <span>开始: {formatDateTime(agent.started_at)}</span>
              <span>完成: {formatDateTime(agent.completed_at)}</span>
            </div>
            {agent.error_message ? <p className="risk-text">错误: {agent.error_message}</p> : null}
          </article>
        ))}
      </div>
    </Card>
  );
}

export function ResearchEventTimeline({
  events,
  connectionState,
}: {
  events: ProjectEvent[];
  connectionState: 'connecting' | 'open' | 'reconnecting' | 'fallback';
}) {
  const tone =
    connectionState === 'open' ? 'success' : connectionState === 'reconnecting' ? 'warning' : connectionState === 'fallback' ? 'danger' : 'neutral';

  return (
    <Card>
      <SectionHeading
        eyebrow="Event Stream"
        title="研究时间线"
        description="SSE 断开时保留最后已知状态，并提示连接恢复中。"
        actions={<Badge tone={tone}>{connectionState}</Badge>}
      />
      <div className="timeline">
        {events.length === 0 ? (
          <EmptyState title="还没有事件" description="项目创建后，阶段推进、证据采集和决策都会出现在这里。" />
        ) : (
          events
            .slice()
            .sort((a, b) => b.sequence_number - a.sequence_number)
            .map((event) => {
              const preset = EVENT_COPY[event.event_type] ?? { tone: 'neutral' as const };
              return (
                <article className="timeline__item" key={event.event_id}>
                  <Badge tone={preset.tone}>{describeEvent(event)}</Badge>
                  <div>
                    <strong>#{event.sequence_number}</strong>
                    <p>{formatDateTime(event.timestamp)}</p>
                  </div>
                </article>
              );
            })
        )}
      </div>
    </Card>
  );
}

export function EvidenceListPanel({ projectId, evidence, claims }: { projectId: string; evidence: Evidence[]; claims: Claim[] }) {
  const queryClient = useQueryClient();
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [title, setTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [excerpt, setExcerpt] = useState('');
  const [status, setStatus] = useState<'verified' | 'partially_verified' | 'unverified'>('partially_verified');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceOptions = useMemo(() => ['all', ...Array.from(new Set(evidence.map((item) => item.source_type)))], [evidence]);
  const filtered = sourceFilter === 'all' ? evidence : evidence.filter((item) => item.source_type === sourceFilter);
  const statusOptions = [
    { value: 'partially_verified' as const, label: '部分验证' },
    { value: 'verified' as const, label: '已验证' },
    { value: 'unverified' as const, label: '未验证' },
  ];
  const selectedStatusLabel = statusOptions.find((option) => option.value === status)?.label ?? statusOptions[0].label;

  async function handleIngest(event: FormEvent<HTMLFormElement>): Promise<void> {
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
        status,
        collected_at: new Date().toISOString(),
        confidence: status === 'verified' ? 0.9 : 0.7,
        authority_score: status === 'verified' ? 0.9 : 0.7,
        recency_score: 0.8,
        diversity_score: 0.7,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workspace', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
      ]);
      if (status !== 'unverified') {
        await api.retryInitialResearch(projectId);
      }
      setTitle('');
      setSourceUrl('');
      setExcerpt('');
    } catch {
      setError('证据保存失败，请检查来源链接和后端服务。');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <SectionHeading eyebrow="Evidence Lake" title="证据中心" description="来源、可信度、状态和缺口要同时可见。" />
      <form className="evidence-ingest-form" onSubmit={handleIngest}>
        <strong>人工录入用户证据</strong>
        <p className="muted-copy">请输入真实评论或访谈内容，并填写可追溯的来源链接。</p>
        <div className="evidence-ingest-form__grid">
          <label className="ui-field"><span>标题</span><input className="ui-input" required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：用户对夜间误报的反馈" /></label>
          <label className="ui-field"><span>来源链接</span><input className="ui-input" required type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." /></label>
        </div>
        <label className="ui-field"><span>评论 / 访谈原文</span><textarea className="ui-textarea" required value={excerpt} onChange={(event) => setExcerpt(event.target.value)} placeholder="粘贴真实用户评论或访谈片段" /></label>
        <div className="evidence-ingest-form__actions">
          <label className="ui-field">
            <span>审核状态</span>
            <SelectField
              ariaLabel="审核状态"
              onChange={(nextLabel) => {
                const nextStatus = statusOptions.find((option) => option.label === nextLabel)?.value;
                if (nextStatus) {
                  setStatus(nextStatus);
                }
              }}
              options={statusOptions.map((option) => option.label)}
              value={selectedStatusLabel}
            />
          </label>
          <Button type="submit" disabled={submitting}>{submitting ? '保存中…' : '保存证据'}</Button>
        </div>
        {error ? <p className="form-error">{error}</p> : null}
      </form>
      <div className="toolbar">
        <label className="ui-field">
          <span>来源类型</span>
          <SelectField ariaLabel="来源类型" onChange={setSourceFilter} options={sourceOptions} value={sourceFilter} />
        </label>
      </div>
      <div className="evidence-list">
        {filtered.length === 0 ? (
          <EmptyState title="当前筛选下没有证据" description="可以切换来源类型，或者等待新证据入湖。" />
        ) : (
          filtered.map((item) => {
            const supportingClaims = claims.filter((claim) => claim.evidence_ids.includes(item.evidence_id));
            const contradictingClaims = claims.filter((claim) => claim.contradicting_evidence_ids.includes(item.evidence_id));
            return (
              <article className="evidence-card" key={item.evidence_id}>
                <div className="evidence-card__header">
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.evidence_id}</p>
                  </div>
                  <div className="cluster">
                    <Badge tone={item.status === 'failed' ? 'danger' : 'success'}>{item.status}</Badge>
                    <Badge tone="neutral">{item.source_type}</Badge>
                  </div>
                </div>
                <p>{item.excerpt}</p>
                <div className="evidence-card__meta">
                  <span>可信度 {formatPercent(item.confidence)}</span>
                  <span>{formatDateTime(item.captured_at)}</span>
                  <a href={item.source_url} rel="noreferrer" target="_blank">
                    打开来源
                  </a>
                </div>
                <div className="cluster">
                  {supportingClaims.map((claim) => (
                    <Badge key={claim.claim_id} tone="accent">
                      支持 {claim.claim_id}
                    </Badge>
                  ))}
                  {contradictingClaims.map((claim) => (
                    <Badge key={claim.claim_id} tone="warning">
                      反驳 {claim.claim_id}
                    </Badge>
                  ))}
                </div>
              </article>
            );
          })
        )}
      </div>
    </Card>
  );
}

export function ClaimEvidenceGraph({ claims }: { claims: Claim[] }) {
  return (
    <Card>
      <SectionHeading eyebrow="Claims" title="Claim 审视" description="缺证 Claim 必须显式标红，不能静默消失。" />
      <div className="claim-list">
        {claims.map((claim) => (
          <article className={`claim-card${claim.evidence_ids.length === 0 ? ' claim-card--warning' : ''}`} key={claim.claim_id}>
            <div className="claim-card__header">
              <strong>{claim.claim_id}</strong>
              <Badge tone={claim.evidence_ids.length === 0 ? 'danger' : 'accent'}>{claim.status}</Badge>
            </div>
            <p>{claim.statement}</p>
            <div className="cluster">
              <span>支持证据: {claim.evidence_ids.join(', ') || '无'}</span>
              <span>反驳证据: {claim.contradicting_evidence_ids.join(', ') || '无'}</span>
            </div>
          </article>
        ))}
      </div>
    </Card>
  );
}

export function ConceptComparisonBoard({ concepts }: { concepts: Concept[] }) {
  const active = concepts.filter((item) => item.status !== 'rejected');
  const rejected = concepts.filter((item) => item.status === 'rejected');

  const renderConcept = (concept: Concept) => (
    <article className="concept-card" key={concept.concept_id}>
      <div className="concept-card__header">
        <div>
          <h3>{concept.name}</h3>
          <p>{concept.target_user}</p>
        </div>
        <Badge tone={concept.status === 'rejected' ? 'danger' : 'accent'}>{concept.status}</Badge>
      </div>
      <p className="concept-card__value">{concept.value_proposition}</p>
      <div className="score-grid">
        {Object.entries(concept.scores).map(([key, value]) => (
          <Stat key={key} label={titleCaseKey(key)} value={value.toFixed(1)} />
        ))}
      </div>
      <div className="concept-card__group">
        <strong>支持证据</strong>
        <p>{concept.supporting_evidence_ids.join(', ') || '暂无支持证据'}</p>
      </div>
      <div className="concept-card__group">
        <strong>关键风险</strong>
        <ul>
          {concept.risks.map((risk) => (
            <li key={risk}>{risk}</li>
          ))}
        </ul>
      </div>
      <div className="concept-card__group">
        <strong>红队发现</strong>
        <ul>
          {concept.red_team_findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      </div>
    </article>
  );

  if (concepts.length === 0) {
    return (
      <Card>
        <SectionHeading eyebrow="Concept Arena" title="候选概念竞技场" />
        <EmptyState title="候选概念尚未生成" description="当前项目还在实时调研阶段，生成概念后会自动出现在这里。" />
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeading eyebrow="Concept Arena" title="候选概念竞技场" description="被淘汰概念保留痕迹，默认折叠到下方。" />
      <div className="concept-grid">{active.map(renderConcept)}</div>
      {rejected.length > 0 ? (
        <details className="rejected-section">
          <summary>已淘汰概念 ({rejected.length})</summary>
          <div className="concept-grid concept-grid--rejected">{rejected.map(renderConcept)}</div>
        </details>
      ) : null}
    </Card>
  );
}

export function ReportEvidenceInspector({ report, claims }: { report: Report | null; claims: Claim[] }) {
  if (!report) {
    return <EmptyState title="最终提案尚未生成" description="批准概念后，这里会展示可追溯的最终建议与证据映射。" />;
  }

  return (
    <Card>
      <SectionHeading eyebrow="Final Proposal" title="提案与引用审视" description={`版本 ${report.version} · ${formatDateTime(report.generated_at)}`} />
      <div className="proposal-layout">
        <div className="proposal-layout__main">
          <Card className="proposal-summary">
            <h3>最终建议</h3>
            <p>{report.recommendation}</p>
          </Card>
          {Object.entries(report.sections).map(([key, value]) => (
            <Card key={key} className="proposal-section">
              <h3>{titleCaseKey(key)}</h3>
              {Array.isArray(value) ? (
                <ul>
                  {value.map((item, index) => (
                    <li key={`${key}-${index}`}>{String(item)}</li>
                  ))}
                </ul>
              ) : (
                <p>{String(value)}</p>
              )}
            </Card>
          ))}
        </div>
        <aside className="proposal-layout__aside">
          <Card>
            <h3>引用证据</h3>
            <div className="cluster">
              {report.cited_evidence_ids.map((item) => (
                <Badge key={item} tone="accent">
                  {item}
                </Badge>
              ))}
            </div>
          </Card>
          <Card>
            <h3>未知问题</h3>
            <ul>
              {report.unknowns.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Card>
          <Card>
            <h3>Claim 风险</h3>
            <ul>
              {claims
                .filter((item) => item.evidence_ids.length === 0)
                .map((item) => (
                  <li key={item.claim_id}>{item.statement}</li>
                ))}
            </ul>
          </Card>
        </aside>
      </div>
    </Card>
  );
}

export function MetricsSummaryPanel({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) {
    return <EmptyState title="还没有方法对比数据" description="报告阶段完成后，这里会出现质量、效率和成本指标。" />;
  }

  return (
    <Card>
      <SectionHeading eyebrow="Method Comparison" title="方法对比与质量指标" description="先看核心指标，再看 AI 与传统流程对照。" />
      <div className="score-grid">
        {summarizeMetrics(metrics).map((item) => (
          <Stat key={item.label} label={item.label} value={item.value} />
        ))}
        <Stat label="总耗时" value={`${Math.round(metrics.elapsed_seconds / 60)} 分钟`} />
        <Stat label="预计成本" value={formatCurrency(metrics.estimated_cost)} />
      </div>
      <div className="comparison-table">
        {Object.entries(metrics.comparison).map(([key, value]) => (
          <div className="comparison-table__row" key={key}>
            <span>{titleCaseKey(key)}</span>
            <strong>{String(value)}</strong>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function ProjectOverviewSidebar({
  project,
  metrics,
  events,
}: {
  project: Project;
  metrics: Metrics | null;
  events: ProjectEvent[];
}) {
  const latestFailure = events.find((item) => item.event_type === 'evidence_failed');
  const latestDecision = project.pending_decision?.gate ?? '无';

  return (
    <div className="sidebar-stack">
      <Card>
        <SectionHeading eyebrow="项目状态" title={project.brief.category} description={project.brief.target_user} />
        <div className="score-grid score-grid--tight">
          <Stat label="阶段" value={STATUS_LABELS[project.status]} />
          <Stat label="进度" value={`${project.progress}%`} />
          <Stat label="Gate" value={latestDecision} />
          <Stat label="更新" value={formatDateTime(project.updated_at)} />
        </div>
      </Card>
      <Card>
        <h3>风险提醒</h3>
        <ul className="risk-list">
          <li>最终结论必须能追溯到有效 Evidence IDs。</li>
          <li>概念晋级前必须看见红队意见和空证据 Claim。</li>
          {latestFailure ? <li>最近一次采集失败仍保留在覆盖缺口中。</li> : null}
        </ul>
      </Card>
      <Card>
        <h3>指标速览</h3>
        <div className="score-grid score-grid--tight">
          {summarizeMetrics(metrics).map((item) => (
            <Stat key={item.label} label={item.label} value={item.value} />
          ))}
        </div>
      </Card>
    </div>
  );
}

export function BriefReviewPanel({ brief, status }: { brief: ResearchBrief; status: Project['status'] }) {
  return (
    <Card>
      <SectionHeading
        eyebrow="Brief Review"
        title="研究任务定义"
        description={status === 'awaiting_brief_approval' ? '当前正等待人工确认 brief。' : '研究范围已锁定。'}
      />
      <div className="brief-layout">
        <Card className="brief-card">
          <h3>核心问题</h3>
          <p>{brief.question}</p>
        </Card>
        <div className="brief-grid">
          <Card>
            <h3>目标用户</h3>
            <p>{brief.target_user}</p>
          </Card>
          <Card>
            <h3>区域</h3>
            <p>{brief.region}</p>
          </Card>
          <Card>
            <h3>场景</h3>
            <ul>{brief.scenarios.map((item) => <li key={item}>{item}</li>)}</ul>
          </Card>
          <Card>
            <h3>约束</h3>
            <ul>{brief.constraints.map((item) => <li key={item}>{item}</li>)}</ul>
          </Card>
        </div>
        <Card>
          <h3>焦点维度</h3>
          <div className="cluster">
            {brief.focus_dimensions.map((item) => (
              <Badge key={item} tone="accent">
                {item}
              </Badge>
            ))}
          </div>
        </Card>
      </div>
    </Card>
  );
}

export function ProjectCreationPanel({
  onSubmit,
  busy,
  embedded = false,
}: {
  onSubmit: (brief: ResearchBrief) => Promise<void> | void;
  busy: boolean;
  embedded?: boolean;
}) {
  const defaultCategory = '家庭安防';
  const [brief, setBrief] = useState<ResearchBrief>({
    question: 'eufy 是否应该为北美租房用户设计一套低安装门槛、可迁移、低订阅依赖的家庭安防方案？',
    category: defaultCategory,
    target_user: '北美租房家庭与合租用户',
    region: '美国 / 加拿大',
    scenarios: ['门口访客', '搬家迁移'],
    constraints: ['免打孔', '低订阅依赖'],
    focus_dimensions: ['安装', '迁移'],
  });
  const [selectedCategoryGroup, setSelectedCategoryGroup] = useState<string>(() => findCategoryGroupLabel(defaultCategory));
  const [showAdvanced, setShowAdvanced] = useState(false);

  const categoryOptions = useMemo(() => getCategoryOptions(selectedCategoryGroup), [selectedCategoryGroup]);

  const formContent = (
    <>
      <SectionHeading eyebrow="Task Draft" title="起草研究任务" />
      <div className="project-creation-panel__presets">
        <Badge tone="accent">标准调研流</Badge>
        <Badge tone="neutral">Research / Evidence / Red Team</Badge>
        <Badge tone="neutral">桌面优先审批台</Badge>
      </div>
      <form
        className="project-form"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit(brief);
        }}
      >
        <section className="project-form__section">
          <div className="project-form__section-header">
            <strong>核心问题</strong>
          </div>
          <label className="ui-field">
            <textarea
              className="ui-textarea"
              value={brief.question}
              onChange={(event) => setBrief((current) => ({ ...current, question: event.target.value }))}
            />
          </label>
        </section>

        <section className="project-form__section">
          <div className="project-form__section-header">
            <strong>基础范围</strong>
            <span>先确定品类、用户和区域。</span>
          </div>
          <div className="project-form__grid">
            <label className="ui-field">
              <span>品类</span>
              <div className="ui-select-stack">
                <SelectField
                  ariaLabel="一级产品线"
                  onChange={(nextGroup) => {
                    const nextOptions = getCategoryOptions(nextGroup);
                    setSelectedCategoryGroup(nextGroup);
                    setBrief((current) => ({ ...current, category: nextOptions[0] ?? current.category }));
                  }}
                  options={EUFY_CATEGORY_GROUPS.map((group) => group.label)}
                  value={selectedCategoryGroup}
                />
                <SelectField
                  ariaLabel="二级品类"
                  onChange={(nextCategory) => setBrief((current) => ({ ...current, category: nextCategory }))}
                  options={categoryOptions}
                  value={brief.category}
                />
              </div>
            </label>
            <label className="ui-field">
              <span>目标用户</span>
              <input
                className="ui-input"
                value={brief.target_user}
                onChange={(event) => setBrief((current) => ({ ...current, target_user: event.target.value }))}
              />
            </label>
            <label className="ui-field">
              <span>区域</span>
              <SelectField
                ariaLabel="区域"
                onChange={(nextRegion) => setBrief((current) => ({ ...current, region: nextRegion }))}
                options={REGION_OPTIONS}
                value={brief.region}
              />
            </label>
          </div>
        </section>

        <section className="project-form__section">
          <div className="project-form__section-header">
            <strong>高级范围</strong>
            <button className="project-form__toggle" onClick={() => setShowAdvanced((current) => !current)} type="button">
              {showAdvanced ? '收起高级范围' : '展开高级范围'}
            </button>
          </div>
          <div className="project-form__summary">
            <span>场景：{summarizeMultiple(brief.scenarios)}</span>
            <span>约束：{summarizeMultiple(brief.constraints)}</span>
            <span>焦点：{summarizeMultiple(brief.focus_dimensions)}</span>
          </div>
          {showAdvanced ? (
            <div className="project-form__grid project-form__grid--three">
              <label className="ui-field">
                <span>场景</span>
                <MultiSelectPopover
                  label="场景"
                  onChange={(nextScenarios) => setBrief((current) => ({ ...current, scenarios: nextScenarios }))}
                  options={SCENARIO_OPTIONS}
                  value={brief.scenarios}
                />
              </label>
              <label className="ui-field">
                <span>约束</span>
                <MultiSelectPopover
                  label="约束"
                  onChange={(nextConstraints) => setBrief((current) => ({ ...current, constraints: nextConstraints }))}
                  options={CONSTRAINT_OPTIONS}
                  value={brief.constraints}
                />
              </label>
              <label className="ui-field">
                <span>焦点维度</span>
                <MultiSelectPopover
                  label="焦点维度"
                  onChange={(nextFocusDimensions) => setBrief((current) => ({ ...current, focus_dimensions: nextFocusDimensions }))}
                  options={FOCUS_DIMENSION_OPTIONS}
                  value={brief.focus_dimensions}
                />
              </label>
            </div>
          ) : null}
        </section>

        <div className="project-form__footer">
          <Button type="submit" disabled={busy}>
            {busy ? '创建中...' : '创建项目'}
          </Button>
        </div>
      </form>
    </>
  );

  if (embedded) {
    return <div className="project-creation-panel project-creation-panel--embedded">{formContent}</div>;
  }

  return <Card className="project-creation-panel">{formContent}</Card>;
}

export function NextActionPanel({ projects }: { projects: Project[] }) {
  const sortedProjects = [...projects].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at));
  const priorityProject =
    sortedProjects.find((project) => project.pending_decision) ??
    sortedProjects.find((project) => ['researching', 'supplementing_research', 'generating_report'].includes(project.status)) ??
    sortedProjects[0];

  if (!priorityProject) {
    return (
      <section className="home-section home-section--primary next-action-panel">
        <SectionHeading className="section-heading--accent-title" title="NEXT ACTION" />
        <div className="home-empty">
          <strong>还没有可分发的研究任务</strong>
          <p>点击左侧“新建研究”，先创建第一条研究项目。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-section home-section--primary next-action-panel">
      <SectionHeading className="section-heading--accent-title" title="NEXT ACTION" />
      <div className="next-action-panel__body">
        <div className="next-action-panel__content">
          <div className="cluster">
            <Badge tone={getProjectBadgeTone(priorityProject.status)}>{STATUS_LABELS[priorityProject.status]}</Badge>
            {priorityProject.pending_decision ? <Badge tone="warning">{getDecisionGateLabel(priorityProject)} gate</Badge> : null}
          </div>
          <h3>{priorityProject.brief.category}</h3>
          <p>{getActivityLine(priorityProject)}，需要你决定是否继续推进。</p>
          <div className="next-action-panel__meta">
            <span>{getStageLabel(priorityProject.current_stage)}</span>
            <span>{formatDateTime(priorityProject.updated_at)}</span>
          </div>
        </div>
        <div className="next-action-panel__actions">
          <Link className="ui-button ui-button--primary" to={`/projects/${priorityProject.project_id}`}>
            立即处理
          </Link>
          <Link className="ui-button ui-button--ghost" to={`/projects/${priorityProject.project_id}`}>
            查看项目
          </Link>
        </div>
      </div>
    </section>
  );
}

export function ContinueWorkingPanel({ projects }: { projects: Project[] }) {
  const items = [...projects].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)).slice(0, 3);

  return (
    <section className="home-section">
      <SectionHeading className="section-heading--accent-title" title="CONTINUE WORKING" />
      {items.length === 0 ? (
        <div className="home-empty">
          <strong>暂无项目</strong>
          <p>创建研究后，这里只保留最近的 3 个项目入口。</p>
        </div>
      ) : (
        <div className="work-list">
          {items.map((project) => (
            <Link className="work-list__item" key={project.project_id} to={`/projects/${project.project_id}`}>
              <div className="work-list__main">
                <div className="work-list__header">
                  <strong>{project.brief.category}</strong>
                  <Badge tone={getProjectBadgeTone(project.status)}>{STATUS_LABELS[project.status]}</Badge>
                </div>
                <p>{getStageLabel(project.current_stage)}</p>
              </div>
              <div className="work-list__meta">
                <span>{project.pending_decision ? `${getDecisionGateLabel(project)} gate` : `${project.progress}%`}</span>
                <span>{formatDateTime(project.updated_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export function ProjectsWorkspaceLaunchpad({ projects }: { projects: Project[] }) {
  const sortedProjects = [...projects].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at));
  const decisionProject = sortedProjects.find((project) => project.pending_decision);
  const liveProject = sortedProjects.find((project) =>
    ['researching', 'supplementing_research', 'generating_report'].includes(project.status),
  );
  const recentProject = sortedProjects[0];

  return (
    <Card>
      <SectionHeading
        eyebrow="Workspace Flow"
        title="继续工作"
        description="像工作台一样进入当前上下文，而不是每次都从空白创建开始。"
      />
      <div className="launchpad-grid">
        <Link className="launchpad-card launchpad-card--highlight" to={recentProject ? `/projects/${recentProject.project_id}` : '/projects'}>
          <div className="launchpad-card__header">
            <Badge tone="accent">继续上次研究</Badge>
            <span>{recentProject ? formatDateTime(recentProject.updated_at) : '暂无项目'}</span>
          </div>
          <strong>{recentProject ? recentProject.brief.question : '先创建第一条研究任务'}</strong>
          <p>{recentProject ? getProjectPriorityLine(recentProject) : '创建后会自动进入项目工作台。'}</p>
        </Link>

        <Link className="launchpad-card" to={decisionProject ? `/projects/${decisionProject.project_id}` : '/projects'}>
          <div className="launchpad-card__header">
            <Badge tone={decisionProject ? 'warning' : 'neutral'}>待你决策</Badge>
            <span>{decisionProject ? STATUS_LABELS[decisionProject.status] : '当前为空'}</span>
          </div>
          <strong>{decisionProject ? decisionProject.brief.category : '没有待处理 gate'}</strong>
          <p>{decisionProject ? `${getDecisionGateLabel(decisionProject)} gate 需要人工确认。` : '新的人工 gate 会优先出现在这里。'}</p>
        </Link>

        <Link className="launchpad-card" to={liveProject ? `/projects/${liveProject.project_id}` : '/projects'}>
          <div className="launchpad-card__header">
            <Badge tone={liveProject ? 'accent' : 'neutral'}>Agent 正在运行</Badge>
            <span>{liveProject ? `${liveProject.progress}%` : '空闲'}</span>
          </div>
          <strong>{liveProject ? liveProject.brief.category : '当前没有活跃研究流'}</strong>
          <p>{liveProject ? liveProject.current_stage : '创建项目后，运行状态会在这里持续更新。'}</p>
        </Link>
      </div>
    </Card>
  );
}

export function ProjectDecisionQueue({ projects }: { projects: Project[] }) {
  const pendingProjects = [...projects]
    .filter((project) => project.pending_decision)
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at));

  if (pendingProjects.length === 0) {
    return (
      <Card>
        <SectionHeading eyebrow="Decision Queue" title="待审批" description="当前没有需要人工处理的 gate。" />
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeading eyebrow="Decision Queue" title="待审批" description="优先处理会阻塞研究推进的人工作业。" />
      <div className="stack-list">
        {pendingProjects.map((project) => (
          <Link className="queue-card" key={project.project_id} to={`/projects/${project.project_id}`}>
            <div className="queue-card__header">
              <strong>{project.brief.category}</strong>
              <Badge tone="warning">{getDecisionGateLabel(project)} gate</Badge>
            </div>
            <p>{project.brief.target_user}</p>
            <div className="queue-card__meta">
              <span>{STATUS_LABELS[project.status]}</span>
              <span>{formatDateTime(project.updated_at)}</span>
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}

export function ProjectActivityRail({ projects }: { projects: Project[] }) {
  const items = [...projects]
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))
    .slice(0, 5);

  if (items.length === 0) {
    return (
      <section className="home-section">
        <SectionHeading className="section-heading--accent-title" title="RECENT ACTIVITY" />
        <div className="home-empty">
          <strong>还没有最近动态</strong>
          <p>创建项目后，这里会开始汇总研究推进和人工 gate。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-section">
      <SectionHeading className="section-heading--accent-title" title="RECENT ACTIVITY" />
      <div className="activity-list">
        {items.map((project) => (
          <Link className="activity-list__item" key={project.project_id} to={`/projects/${project.project_id}`}>
            <div className="activity-list__row">
              <Badge tone={getProjectBadgeTone(project.status)}>{STATUS_LABELS[project.status]}</Badge>
              <span>{formatDateTime(project.updated_at)}</span>
            </div>
            <strong>{project.brief.category}</strong>
            <p>{getActivityLine(project)}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function ProjectsListRail({ projects, currentProjectId }: { projects: Project[]; currentProjectId?: string }) {
  if (projects.length === 0) {
    return (
      <Card>
        <SectionHeading eyebrow="Projects" title="研究项目" description="创建第一条研究任务后，这里会变成快速切换入口。" />
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeading eyebrow="Projects" title="研究项目" description="保留快速切换入口，但每张卡都直接暴露研究状态。" />
      <div className="project-list">
        {projects.map((project) => (
          <Link
            key={project.project_id}
            className={`project-list__item${project.project_id === currentProjectId ? ' project-list__item--active' : ''}`}
            to={`/projects/${project.project_id}`}
          >
            <div className="project-list__content">
              <div className="project-list__header">
                <strong>{project.brief.category}</strong>
                <Badge tone={getProjectBadgeTone(project.status)}>{STATUS_LABELS[project.status]}</Badge>
              </div>
              <p>{project.brief.target_user}</p>
              <div className="project-list__meta">
                <span>{project.current_stage}</span>
                <span>{project.pending_decision ? `${getDecisionGateLabel(project)} gate` : `${project.progress}%`}</span>
                <span>{formatDateTime(project.updated_at)}</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}

export function ViewTabs({
  currentView,
  onChange,
}: {
  currentView: ViewMode;
  onChange: (view: ViewMode) => void;
}) {
  return (
    <div className="view-tabs">
      {(Object.keys(VIEW_LABELS) as ViewMode[]).map((view) => (
        <button
          key={view}
          type="button"
          className={`view-tabs__item${currentView === view ? ' view-tabs__item--active' : ''}`}
          onClick={() => onChange(view)}
        >
          {VIEW_LABELS[view]}
        </button>
      ))}
    </div>
  );
}
