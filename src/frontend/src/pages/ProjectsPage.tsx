import { useEffect, useId, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useCreateProjectMutation, useProjectsQuery, useWorkspaceQuery } from '../shared/api/hooks';
import type { ProjectCreateInput } from '../shared/types/api';
import { api } from '../shared/api/client';
import { EmptyProjectCard, ProjectCard } from '../shared/components/ProjectCard';

const STAGE_LABELS: Record<string, string> = {
  draft: '草稿',
  awaiting_brief_approval: 'Brief 审批',
  researching: '调研中',
  awaiting_concept_approval: '概念审批',
  supplementing_research: '补充调研',
  generating_report: '生成报告',
  awaiting_final_approval: '最终审批',
  completed: '已完成',
  failed: '失败',
  terminated: '已终止',
  brief_confirmation: 'Brief 确认',
  research_planning: '调研规划',
  concept_synthesis: '概念合成',
  final_review: '最终评审',
  scenario_validation: '场景验证',
};

function getWorkflowStepStatus(step: number, progress: number): 'done' | 'current' | '' {
  const thresholds = [0, 10, 25, 45, 60, 75, 100];
  if (progress >= thresholds[step]) return 'done';
  if (step > 0 && progress >= thresholds[step - 1] && progress < thresholds[step]) return 'current';
  return '';
}

type PageId = 'projects' | 'create' | 'brief' | 'research' | 'evidence' | 'users' | 'concepts' | 'scenario' | 'proposal';

function SelectField({
  value,
  options,
  onChange,
  ariaLabel,
  placeholder = '请选择',
}: {
  value: string;
  options: readonly string[];
  onChange: (nextValue: string) => void;
  ariaLabel: string;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  useEffect(() => {
    if (!open) return undefined;

    function handlePointerDown(event: MouseEvent): void {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }

    function handleEscape(event: KeyboardEvent): void {
      if (event.key === 'Escape') setOpen(false);
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
        <span style={{ color: value ? 'inherit' : 'var(--muted)' }}>{value || placeholder}</span>
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
                onClick={() => { onChange(option); setOpen(false); }}
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

export function ProjectsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialPage = (searchParams.get('page') as PageId) || 'projects';
  const navigate = useNavigate();
  const projectsQuery = useProjectsQuery();
  const createProjectMutation = useCreateProjectMutation();
  const projects = projectsQuery.data ?? [];

  const recentProjects = [...projects]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .slice(0, 2);

  const activeProjectId = recentProjects[0]?.project_id ?? '';
  const workspaceQuery = useWorkspaceQuery(activeProjectId);
  const ws = workspaceQuery.data;

  const [activePage, setActivePage] = useState<PageId>(initialPage);
  const [createStep, setCreateStep] = useState(1);

  useEffect(() => {
    const page = (searchParams.get('page') as PageId) || 'projects';
    setActivePage(page);
    if (page === 'create') setCreateStep(1);
  }, [searchParams]);

  useEffect(() => {
    if (ws?.concepts.length) {
      setActiveConcept(ws.concepts[0].concept_id);
    }
  }, [ws?.concepts]);
  const [question, setQuestion] = useState('');
  const [market, setMarket] = useState('');
  const [home, setHome] = useState('');
  const [scope, setScope] = useState('');
  const [direction, setDirection] = useState('');
  const [externalUrl, setExternalUrl] = useState('');

  const [activeInsight, setActiveInsight] = useState(0);
  const [activeConcept, setActiveConcept] = useState('');

  const [scenarioCovered, setScenarioCovered] = useState(false);
  const [scenarioEarly, setScenarioEarly] = useState(false);
  const [scenarioPresent, setScenarioPresent] = useState(true);
  const [rainProb, setRainProb] = useState(87);

  const generatedProjectName = (() => {
    const scopeShort = scope ? scope.split('(')[0].trim() : '';
    const dirLabel = direction === 'AI / 软件能力' ? 'AI 能力' : direction === '新硬件机会' ? '新硬件' : direction === '新使用场景' ? '新场景' : '';
    const parts = ['eufy', scopeShort, dirLabel].filter(Boolean);
    return parts.length > 0 ? `${parts.join(' ')} 研究` : 'eufy 产品机会研究';
  })();

  const generatedValidationPoints = (() => {
    const points: string[] = [];
    if (scope) points.push(`${scope} 的核心用户痛点是什么`);
    if (market) points.push(`${market}市场的独特需求和约束`);
    if (home) points.push(`${home}用户的典型使用场景`);
    if (direction === 'AI / 软件能力') points.push('现有 AI 能力是否足以支持该场景');
    if (direction === '新硬件机会') points.push('新硬件形态是否符合用户安装与使用习惯');
    if (direction === '新使用场景') points.push('场景频次是否足以支撑产品价值');
    points.push('竞品是否已有类似方案');
    points.push('技术落地可行性与成本评估');
    return points.length > 0 ? points : ['产品价值验证', '用户需求确认', '竞品方案调研', '技术可行性评估', '市场匹配度分析'];
  })();

  const computedDecision = (() => {
    if (scenarioCovered) return { text: '不打扰', badge: '保持安静', tone: 'gray' as const, msTime: '—', msg: '包裹处于受遮挡区域，当前不需要提醒。' };
    if (scenarioEarly) return { text: '不打扰', badge: '保持安静', tone: 'gray' as const, msTime: '—', msg: '预计用户在降雨前到家，无需提醒。' };
    if (!scenarioPresent) return { text: '不打扰', badge: '无提醒', tone: 'green' as const, msTime: '—', msg: '包裹已不在门外，无需提醒。' };
    if (rainProb < 40) return { text: '不打扰', badge: '低风险', tone: 'green' as const, msTime: '—', msg: '降雨概率过低，暂不提醒。' };
    if (rainProb < 70) return { text: '可监控', badge: '观望中', tone: 'purple' as const, msTime: '16:00', msg: '降雨概率中等，建议关注后续变化。' };
    return { text: '提醒', badge: '建议采取行动', tone: 'orange' as const, msTime: '16:00', msg: '预计下午 5 点左右开始下雨，你的包裹目前仍在门外。建议在天气变化前尽快取回。' };
  })();

  async function handleStartResearch() {
    const input: ProjectCreateInput = {
      brief: {
        question: question || 'eufy 产品机会研究',
        category: generatedProjectName,
        target_user: home || '未指定',
        region: market || '未指定',
        scenarios: [scope || '暂不限制'],
        constraints: externalUrl ? externalUrl.split('\n').filter(Boolean) : [],
        focus_dimensions: [direction || '暂不限制'],
      },
    };

    const project = await createProjectMutation.mutateAsync(input);
    if (project.pending_decision) {
      await api.submitDecision(project.project_id, {
        decision_id: project.pending_decision.decision_id,
        action: 'approve',
        reason: '从新建流程自动通过 Brief 审批。',
        actor: '用户',
        selected_concept_ids: [],
      });
    }
    navigate(`/projects/${project.project_id}`);
  }

  function jumpTo(target: string) {
    if (target === 'brief') {
      setCreateStep(3);
      setSearchParams({ page: 'brief' });
      setActivePage('brief');
    } else {
      setSearchParams({ page: target });
      setActivePage(target as PageId);
    }
  }

  return (
    <main className="demo-page">
      <div className="demo-top">
        <div>
          <div className="eyebrow">工作区</div>
          <h1>我的产品研究</h1>
        </div>

      </div>

      {/* ── Section: projects ── */}
      <section className={`demo-page-section${activePage === 'projects' ? ' active' : ''}`} id="projects">
        <div className="demo-panel">
          <div className="demo-panel-head">
            <div className="demo-panel-title">我的产品研究</div>
            <button className="demo-btn demo-btn--accent" onClick={() => { setCreateStep(1); setActivePage('create'); }}>＋ 新建产品研究</button>
          </div>
          <div style={{ padding: 14 }}>
            {recentProjects.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(recentProjects.length, 2)}, minmax(0, 1fr))`, gap: 12 }}>
                {recentProjects.map((project) => (
                  <ProjectCard key={project.project_id} project={project} />
                ))}
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                <EmptyProjectCard eyebrow="从这里开始" title="创建你的第一个产品研究" />
                <EmptyProjectCard eyebrow="AI 原生工作流" title="从证据到决策" />
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Section: create ── */}
      <section className={`demo-page-section${activePage === 'create' ? ' active' : ''}`} id="create">
        <div className="demo-panel">
          <div className="demo-panel-head">
            <h2 style={{ fontSize: 20, margin: 0 }}>
              {createStep === 1 ? '你今天想研究什么产品机会？' : createStep === 2 ? '确认研究边界' : '确认研究内容'}
            </h2>
            <span className={`demo-status demo-status--${createStep === 1 ? 'purple' : createStep === 2 ? 'purple' : 'green'}`}>
步骤 {createStep}/3
            </span>
          </div>
          <div style={{ padding: 18 }}>
            {createStep === 1 && (
              <div>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  style={{ width: '100%', minHeight: 150, marginTop: 16, border: '1px solid var(--line)', borderRadius: 12, padding: 14, font: 'inherit', resize: 'vertical' }}
                  placeholder="例如：我想知道 eufy 下一代家庭安防还能做什么。"
                />
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--primary" onClick={() => setCreateStep(2)}>下一步</button>
                  <button className="demo-btn demo-btn--ghost" onClick={() => setActivePage('projects')}>取消</button>
                </div>
              </div>
            )}

            {createStep === 2 && (
              <div>
                <div className="demo-fields">
                  <div className="demo-field">
                    <small>主要市场</small>
                    <SelectField ariaLabel="主要市场" options={['美国', '加拿大', '英国', '德国', '法国', '意大利', '西班牙', '荷兰', '爱尔兰', '希腊', '匈牙利', '克罗地亚', '波兰', '澳大利亚', '新加坡', '新西兰', '越南', '中国台湾', '阿联酋', '全球']} value={market} onChange={setMarket} />
                  </div>
                  <div className="demo-field">
                    <small>住宅类型</small>
                    <SelectField ariaLabel="住宅类型" options={['独栋住宅', '公寓', '租房住宅', '暂不限制']} value={home} onChange={setHome} />
                  </div>
                  <div className="demo-field">
                    <small>产品范围</small>
                    <SelectField ariaLabel="产品范围" options={[
                      '户外安防摄像头 (eufyCam / SoloCam)',
                      '室内安防摄像头 (Indoor Cam / 4G LTE / PoE NVR)',
                      '可视门铃 (Video Doorbell E340 / S330)',
                      '泛光灯 / 墙灯摄像头 (Floodlight / Wall Light Cam)',
                      '智能门锁 (Smart Lock / Video Smart Lock)',
                      '家庭安防中枢 (HomeBase / Smart Display)',
                      '传感器与报警系统 (Entry / Motion / Alarm Kit)',
                      '智能追踪器 (SmartTrack Link / Card)',
                      '安防配件 (Solar Panel / Chime / 支架)',
                      '暂不限制',
                    ]} value={scope} onChange={setScope} />
                  </div>
                  <div className="demo-field">
                    <small>优先探索方向</small>
                    <SelectField ariaLabel="优先探索方向" options={['AI / 软件能力', '新硬件机会', '新使用场景', '暂不限制']} value={direction} onChange={setDirection} />
                  </div>
                </div>
                <div className="demo-field" style={{ marginTop: 14 }}>
                  <small>外部资料链接（可选）</small>
                  <input
                    className="ui-input"
                    placeholder="输入 URL，多个链接请换行输入"
                    style={{ width: '100%', marginTop: 6 }}
                    value={externalUrl}
                    onChange={(e) => setExternalUrl(e.target.value)}
                  />
                </div>
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--ghost" onClick={() => setCreateStep(1)}>返回</button>
                  <button className="demo-btn demo-btn--primary" onClick={() => setCreateStep(3)}>下一步</button>
                </div>
              </div>
            )}

            {createStep === 3 && (
              <div>
                <div className="demo-panel" style={{ boxShadow: 'none', marginTop: 14 }}>
                  <div style={{ padding: 16 }}>
                    <div className="demo-fields">
                      <div className="demo-field"><small>项目名称</small><b>{generatedProjectName}</b></div>
                      <div className="demo-field"><small>地区</small><b>{market}</b></div>
                      <div className="demo-field"><small>住宅类型</small><b>{home}</b></div>
                      <div className="demo-field"><small>产品范围</small><b>{scope}</b></div>
                    </div>
                    <div className="demo-field" style={{ marginTop: 10 }}>
                      <small>核心研究问题</small>
                      <b style={{ fontSize: 12, lineHeight: 1.6 }}>
                        {question || '（请返回第 1 步填写研究问题）'}
                      </b>
                    </div>
                    <div className="demo-field" style={{ marginTop: 10 }}>
                      <small>重点验证</small>
                      <b style={{ fontSize: 11, lineHeight: 1.8 }}>
                        {generatedValidationPoints.map((p, i) => (
                          <span key={i}>{i > 0 && <br />}✓ {p}</span>
                        ))}
                      </b>
                    </div>
                  </div>
                </div>
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--ghost" onClick={() => setCreateStep(2)}>修改研究范围</button>
                  <button className="demo-btn demo-btn--accent" onClick={handleStartResearch} disabled={createProjectMutation.isPending}>
                    {createProjectMutation.isPending ? '创建中...' : '开始 AI 调研'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Section: brief ── */}
      <section className={`demo-page-section${activePage === 'brief' ? ' active' : ''}`} id="brief">
        {ws ? (
          <>
            <div className="demo-metrics">
              <div className="demo-metric"><small>研究市场</small><b>{ws.project.brief.region}</b><span>{ws.project.brief.region}</span></div>
              <div className="demo-metric"><small>核心方向</small><b>{ws.project.brief.focus_dimensions[0] ?? '—'}</b><span>{ws.project.brief.focus_dimensions.join(' / ')}</span></div>
              <div className="demo-metric"><small>核心场景</small><b>{ws.project.brief.scenarios[0] ?? '—'}</b><span>{ws.project.brief.scenarios.join(' × ')}</span></div>
              <div className="demo-metric"><small>当前阶段</small><b style={{ fontSize: 17 }}>{STAGE_LABELS[ws.project.current_stage] ?? ws.project.current_stage}</b><span>{STAGE_LABELS[ws.project.status] ?? ws.project.status}</span></div>
            </div>
            <div className="demo-grid2">
              <div className="demo-panel" style={{ padding: 18 }}>
                <div className="eyebrow" style={{ color: 'var(--accent)', fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>研究简报</div>
                <h2 style={{ fontSize: '1.25rem', margin: '4px 0 14px' }}>{ws.project.brief.question}</h2>
                <div className="demo-fields" style={{ marginTop: 0 }}>
                  <div className="demo-field"><small>品类</small><b>{ws.project.brief.category}</b></div>
                  <div className="demo-field"><small>目标用户</small><b>{ws.project.brief.target_user}</b></div>
                  <div className="demo-field"><small>研究方向</small><b>{ws.project.brief.focus_dimensions.join(' / ')}</b></div>
                  <div className="demo-field"><small>验证场景</small><b>{ws.project.brief.scenarios.join(' × ')}</b></div>
                  <div className="demo-field"><small>约束</small><b>{ws.project.brief.constraints.join(' / ') || '—'}</b></div>
                  <div className="demo-field"><small>进度</small><b>{ws.project.progress}%</b></div>
                </div>
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('research')}>继续进入实时调研</button>
                </div>
              </div>
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <div className="demo-panel-title">AI 原生工作流</div>
                </div>
                <div className="demo-step-list">
                  {[
                    { step: 1, title: '定义问题', desc: '明确研究范围' },
                    { step: 2, title: '收集证据', desc: '用户 / 竞品 / 技术' },
                    { step: 3, title: '用户替身挑战', desc: '不同用户角色' },
                    { step: 4, title: '概念竞争', desc: '专家 + 红队' },
                    { step: 5, title: '场景验证', desc: '反事实测试' },
                    { step: 6, title: '形成产品定义', desc: '最终提案' },
                  ].map(({ step, title, desc }) => {
                    const s = getWorkflowStepStatus(step, ws.project.progress);
                    return (
                      <div className={`demo-step${s ? ` ${s}` : ''}`} key={step}>
                        <div className="num">{step}</div>
                        <div><strong>{title}</strong><span>{desc}</span></div>
                        <span>{s === 'done' ? '已完成' : s === 'current' ? '当前' : '待进行'}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </>
        ) : null}
      </section>

      {/* ── Section: research ── */}
      <section className={`demo-page-section${activePage === 'research' ? ' active' : ''}`} id="research">
        {ws ? (
          <>
            <div className="demo-metrics">
              <div className="demo-metric"><small>研究进度</small><b>{ws.project.progress}%</b><span>{ws.project.current_stage ? STAGE_LABELS[ws.project.current_stage] ?? ws.project.current_stage : ''}</span></div>
              <div className="demo-metric"><small>来源</small><b>{ws.metrics?.source_diversity ?? ws.evidencePage.total}</b><span>{ws.evidencePage.total} 条证据</span></div>
              <div className="demo-metric"><small>有效证据</small><b>{ws.metrics?.valid_evidence_count ?? ws.evidencePage.items.length}</b><span>去重后</span></div>
              <div className="demo-metric"><small>反方证据</small><b>{ws.claims.reduce((sum, c) => sum + c.contradicting_evidence_ids.length, 0)}</b><span>主动保留</span></div>
            </div>
            <div className="demo-research">
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <div className="demo-panel-title">调研流程</div>
                  <span className={`demo-status demo-status--${ws.project.status === 'researching' ? 'green' : 'purple'}`}>{STAGE_LABELS[ws.project.status] ?? ws.project.status}</span>
                </div>
                <div className="demo-pipeline">
                  {ws.agentRuns.map((run) => {
                    const statusColor = run.status === 'completed' ? 'green' : run.status === 'running' ? 'green' : run.status === 'waiting' ? 'purple' : 'gray';
                    return (
                      <div className="demo-pipe" key={run.agent_run_id}>
                        <b>{run.agent_name}</b>
                        <div className="demo-bar"><span style={{ width: `${run.progress}%` }} /></div>
                        <span className={`demo-status demo-status--${statusColor}`}>{run.progress === 100 ? `${run.progress}%` : `${run.progress}%`}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <div className="demo-panel-title">实时动态</div>
                </div>
                <div className="demo-activity">
                  {ws.events.slice(-4).reverse().map((event) => (
                    <div className="demo-event" key={event.event_id}>
                      <b>{event.event_type}</b> {typeof event.data === 'object' ? JSON.stringify(event.data) : String(event.data)}
                    </div>
                  ))}
                </div>
                <div style={{ padding: '0 14px 14px' }}>
                  <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('evidence')}>打开证据中心</button>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </section>

      {/* ── Section: evidence ── */}
      <section className={`demo-page-section${activePage === 'evidence' ? ' active' : ''}`} id="evidence">
        {ws ? (
          <>
            <div className="demo-evidence-layout">
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <div className="demo-panel-title">机会洞察</div>
                </div>
                <div className="demo-insights">
                  {ws.claims.map((claim, i) => (
                    <button key={claim.claim_id} className={`demo-insight${activeInsight === i ? ' active' : ''}`} onClick={() => setActiveInsight(i)}>
                      <strong>{claim.statement.slice(0, 30)}</strong>
                      <span>{claim.statement}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="demo-panel demo-claim">
                <div className="eyebrow" style={{ color: 'var(--accent)' }}>关键结论</div>
                <h2>{ws.claims[0]?.statement ?? '—'}</h2>
                <div className="meta">
                  <span>{ws.claims[0]?.status === 'supported' ? '高置信度' : ws.claims[0]?.status === 'missing_evidence' ? '中等' : '待验证'}</span>
                  <span>{ws.claims[0]?.evidence_ids.length ?? 0} 条证据</span>
                  <span>{new Set(ws.evidencePage.items.filter(e => ws.claims[0]?.evidence_ids.includes(e.evidence_id)).map(e => e.source_type)).size} 个来源</span>
                  <span>{ws.claims[0]?.contradicting_evidence_ids.length ?? 0} 条反方证据</span>
                </div>
                {ws.evidencePage.items.filter(e => ws.claims[0]?.evidence_ids.includes(e.evidence_id)).slice(0, 1).map(e => (
                  <blockquote key={e.evidence_id}>{e.excerpt}</blockquote>
                ))}
                {ws.evidencePage.items.filter(e => ws.claims[0]?.contradicting_evidence_ids.includes(e.evidence_id)).slice(0, 1).map(e => (
                  <blockquote key={e.evidence_id} style={{ borderLeftColor: '#e7b3b3', background: '#fffafa' }}>反方观点：{e.excerpt}</blockquote>
                ))}
              </div>
            </div>
            <div className="demo-actions">
              <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('users')}>进入 AI 用户替身挑战</button>
            </div>
          </>
        ) : null}
      </section>

      {/* ── Section: users ── */}
      <section className={`demo-page-section${activePage === 'users' ? ' active' : ''}`} id="users">
        {ws ? (
          <>
            <div className="demo-personas">
              {ws.evidencePage.items.slice(0, 3).map((evidence) => {
                const sourceTypeLabel = evidence.source_type === 'survey' ? '调查' : evidence.source_type === 'community' ? '社区讨论' : evidence.source_type === 'retail' ? '零售数据' : evidence.source_type;
                return (
                  <div className="demo-persona" key={evidence.evidence_id}>
                    <div className="demo-avatar">{evidence.source_type[0].toUpperCase()}</div>
                    <h3>{evidence.title}</h3>
                    <p>{evidence.excerpt}</p>
                    <blockquote>置信度：{Math.round(evidence.confidence * 100)}%</blockquote>
                    <div className="ground">来源：{sourceTypeLabel} · 状态：{evidence.status}</div>
                  </div>
                );
              })}
            </div>
            <div className="demo-actions">
              <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('concepts')}>进入概念竞技场</button>
            </div>
          </>
        ) : null}
      </section>

      {/* ── Section: concepts ── */}
      <section className={`demo-page-section${activePage === 'concepts' ? ' active' : ''}`} id="concepts">
        {ws ? (
          <>
            <div className="demo-arena">
              <div className="demo-panel">
                <div className="demo-panel-head">
                  <div className="demo-panel-title">概念竞技场</div>
                  <span className="demo-status demo-status--purple">人工评审</span>
                </div>
                <div className="demo-concept-list">
                  {ws.concepts.map((concept) => {
                    const totalScore = Object.values(concept.scores).reduce((sum, v) => sum + v, 0) / Object.keys(concept.scores).length;
                    const scoreBars = Object.values(concept.scores).map((v) => `${v * 10}%`);
                    const statusColor = concept.status === 'rejected' ? 'red' : concept.status === 'candidate' ? 'green' : 'purple';
                    const statusText = concept.status === 'rejected' ? '已淘汰' : concept.status === 'candidate' ? '领先方案' : '待评估';
                    return (
                      <button key={concept.concept_id} className={`demo-concept-btn${activeConcept === concept.concept_id ? ' active' : ''}${concept.status === 'rejected' ? ' rejected' : ''}`} onClick={() => setActiveConcept(concept.concept_id)}>
                        <div className="demo-concept-top">
                          <div>
                            <h3>{concept.name}</h3>
                            <p>{concept.value_proposition}</p>
                          </div>
                          <span className={`demo-status demo-status--${statusColor}`}>{statusText}</span>
                        </div>
                        <div className="demo-scoreline">
                          <div className="demo-score">{totalScore.toFixed(1)}</div>
                          <div className="demo-mini-bars">
                            {scoreBars.map((w, i) => (<div className="demo-mini" key={i}><span style={{ width: w }} /></div>))}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
              {ws.concepts.find(c => c.concept_id === activeConcept) && (
                <div className="demo-panel demo-concept-detail">
                  <div className="eyebrow" style={{ color: 'var(--accent)' }}>领先方案</div>
                  <h2 style={{ fontSize: 18, margin: '4px 0' }}>{ws.concepts.find(c => c.concept_id === activeConcept)!.name}</h2>
                  <div style={{ marginTop: 12 }}>
                    {Object.entries(ws.concepts.find(c => c.concept_id === activeConcept)!.scores).map(([key, val]) => {
                      const label = { desirability: '用户价值', feasibility: '可行性', differentiation: '创新性' }[key] ?? key;
                      return (
                        <div className="demo-score-row" key={key}>
                          <span>{label}</span>
                          <div className="demo-bar"><span style={{ width: `${val * 10}%` }} /></div>
                          <b>{val.toFixed(1)}</b>
                        </div>
                      );
                    })}
                  </div>
                  <div className="demo-panel-title" style={{ marginTop: 14 }}>为什么做 / 为什么不做</div>
                  {ws.concepts.find(c => c.concept_id === activeConcept)!.risks.map((risk, i) => (
                    <div className="demo-reason warn" key={`risk-${i}`}><i>!</i><div>{risk}</div></div>
                  ))}
                  {ws.concepts.find(c => c.concept_id === activeConcept)!.red_team_findings.map((finding, i) => (
                    <div className="demo-reason warn" key={`rt-${i}`}><i>!</i><div>{finding}</div></div>
                  ))}
                </div>
              )}
            </div>
            <div className="demo-actions">
              <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('scenario')}>将优胜概念送入场景智能实验室</button>
            </div>
          </>
        ) : null}
      </section>

      {/* ── Section: scenario ── */}
      <section className={`demo-page-section${activePage === 'scenario' ? ' active' : ''}`} id="scenario">
        <div className="demo-metrics">
          <div className="demo-metric"><small>场景理解置信度</small><b>92%</b><span>上下文完整度</span></div>
          <div className="demo-metric"><small>未来风险</small><b>81%</b><span>未来 3 小时</span></div>
          <div className="demo-metric"><small>行动提前量</small><b>60 分钟</b><span>风险发生前</span></div>
          <div className="demo-metric"><small>当前决策</small><b style={{ fontSize: 17 }}>{computedDecision.text}</b><span>也可以不打扰</span></div>
        </div>
        <div className="demo-scenario-grid">
          <div className="demo-panel">
            <div className="demo-panel-head">
              <div className="demo-panel-title">实时上下文 / 世界状态</div>
            </div>
            <div className="demo-context">
              <div className="demo-ctx-group">
                <div className="demo-ctx-title">事件</div>
                <div className="demo-ctx-row"><span>检测到包裹</span><b>14:05</b></div>
                <div className="demo-ctx-row"><span>是否仍在门外</span><b>{scenarioPresent ? '是' : '否'}</b></div>
              </div>
              <div className="demo-ctx-group">
                <div className="demo-ctx-title">环境</div>
                <div className="demo-ctx-row"><span>预计降雨</span><b>17:00</b></div>
                <div className="demo-ctx-row"><span>降雨概率</span><b>{rainProb}%</b></div>
              </div>
              <div className="demo-ctx-group">
                <div className="demo-ctx-title">家庭状态</div>
                <div className="demo-ctx-row"><span>当前是否有人</span><b>无人</b></div>
                <div className="demo-ctx-row"><span>预计返家</span><b>18:30</b></div>
                <div className="demo-ctx-row"><span>门廊状态</span><b>无遮挡</b></div>
              </div>
              <div className="demo-ctx-group">
                <div className="demo-ctx-title">反事实测试</div>
                <div className="demo-switchrow"><span>门廊有遮挡</span>
                  <label className="demo-switch"><input type="checkbox" checked={scenarioCovered} onChange={(e) => setScenarioCovered(e.target.checked)} /><span className="demo-slider" /></label>
                </div>
                <div className="demo-switchrow"><span>用户在降雨前返家</span>
                  <label className="demo-switch"><input type="checkbox" checked={scenarioEarly} onChange={(e) => setScenarioEarly(e.target.checked)} /><span className="demo-slider" /></label>
                </div>
                <div className="demo-switchrow"><span>包裹仍在门外</span>
                  <label className="demo-switch"><input type="checkbox" checked={scenarioPresent} onChange={(e) => setScenarioPresent(e.target.checked)} /><span className="demo-slider" /></label>
                </div>
                <div style={{ marginTop: 9 }}>
                  <label style={{ fontSize: 10, color: 'var(--muted)' }}>降雨概率：<b>{rainProb}%</b></label>
                  <input className="demo-range" type="range" min={0} max={100} value={rainProb} onChange={(e) => setRainProb(Number(e.target.value))} />
                </div>
              </div>
            </div>
          </div>
          <div className="demo-intel">
            <div className="demo-intel-box">
              <div className="demo-panel-title" style={{ color: 'var(--muted)' }}>场景理解</div>
              <h3>{scenarioCovered ? '门廊有遮挡，包裹不会受到降雨影响。' : scenarioEarly ? '用户将在降雨前返家，包裹无需担心。' : !scenarioPresent ? '包裹已不在门外，无需关注。' : rainProb < 40 ? '降雨可能性较低，暂无明显风险。' : '包裹可能会在即将到来的降雨中持续暴露。'}</h3>
              <p>{scenarioCovered || scenarioEarly || !scenarioPresent ? '当前条件已消除风险因素。' : rainProb < 40 ? '当前降雨概率不足以触发提醒。' : '包裹仍在无遮雨门廊，家庭无人，而降雨时间早于预计返家时间。'}</p>
            </div>
            <div className="demo-intel-box">
              <div className="demo-panel-title" style={{ color: 'var(--muted)' }}>未来状态预测</div>
              <div className="demo-timeline">
                <div className="demo-time"><small>15:30</small><b>包裹仍在门外</b></div>
                <div className="demo-time"><small>16:00</small><b>最佳行动窗口</b></div>
                <div className="demo-time risk"><small>17:00</small><b>开始降雨</b></div>
                <div className="demo-time risk"><small>17:20</small><b>暴露风险 {computedDecision.text === '不打扰' ? '5%' : `${rainProb}%`}</b></div>
              </div>
            </div>
            <div className="demo-intel-box">
              <div className="demo-panel-title" style={{ color: 'var(--muted)' }}>干预策略</div>
              <div className="demo-actionbox">
                <span className={`demo-status demo-status--${computedDecision.tone}`}>{computedDecision.badge}</span>
                <strong>{computedDecision.msTime}</strong>
                <div className="demo-message">{computedDecision.msg}</div>
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--primary">批准提醒</button>
                  <button className="demo-btn demo-btn--ghost">过度打扰</button>
                  <button className="demo-btn demo-btn--ghost">不采取行动</button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="demo-why">
          <b>为什么这能证明 Level 4？</b><br />
          如果把"门廊有遮挡""用户会提前回家""降雨概率降低""包裹已经被取走"这些条件逐个改变，最终决策应该随上下文合理变化。这样可以证明系统不是简单的"包裹 + 下雨 = 提醒"。
        </div>
        <div className="demo-actions">
          <button className="demo-btn demo-btn--accent" onClick={() => jumpTo('proposal')}>生成最终产品提案</button>
        </div>
      </section>

      {/* ── Section: proposal ── */}
      <section className={`demo-page-section${activePage === 'proposal' ? ' active' : ''}`} id="proposal">
        <div className="demo-proposal">
          <div className="demo-panel demo-proposal-main">
            <div className="eyebrow" style={{ color: 'var(--accent)' }}>最终产品提案 · 演示</div>
            <h2>eufy 情境智能 AI</h2>
            <div className="demo-section">
              <h3>产品机会</h3>
              <p>传统家庭安防主要识别"发生了什么"，但真实用户决策往往依赖天气、时间、家庭是否有人、设备状态和未来变化。产品机会是把这些上下文组合成一个场景，并在风险发生前采取行动。</p>
            </div>
            <div className="demo-section">
              <h3>核心能力</h3>
              <div className="demo-features">
                <div className="demo-feature">多上下文世界状态</div>
                <div className="demo-feature">场景理解</div>
                <div className="demo-feature">未来状态预测</div>
                <div className="demo-feature">主动干预</div>
                <div className="demo-feature">反事实验证</div>
                <div className="demo-feature">隐私控制</div>
              </div>
            </div>
            <div className="demo-section">
              <h3>首个演示场景</h3>
              <p>包裹 × 天气 × 无人在家。天气只是上下文之一，而不是产品本身。</p>
            </div>
            <div className="demo-section">
              <h3>核心原则</h3>
              <p><b>不是提醒更多，而是理解更深。</b>真正高级的系统要知道什么时候主动帮助，也知道什么时候保持安静。</p>
            </div>
          </div>
          <div>
            <div className="demo-panel demo-compare">
              <div className="demo-panel-title">AI 原生 vs 经验驱动</div>
              {[
                ['指标', '传统', 'AI 原生'],
                ['证据来源', '11', '31'],
                ['反方证据', '2', '27'],
                ['候选概念', '1–2', '3'],
                ['淘汰理由', '弱', '完整保留'],
                ['反事实验证', '无', '有'],
                ['决策可追溯性', '低', '高'],
              ].map((row, i) => (
                <div className="demo-compare-row" key={i}>
                  <span>{row[0]}</span><span>{row[1]}</span><span>{row[2]}</span>
                </div>
              ))}
            </div>
            <div className="demo-callout">
              <b>比赛核心表达：</b><br />
              传统产品经理往往先有一个想法，再寻找支持它的证据；AI 原生工作流先构建证据与反证，再让用户替身、专家、红队和场景实验持续挑战方案，最后才进入产品定义。
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
