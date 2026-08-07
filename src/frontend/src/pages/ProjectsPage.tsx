import { useEffect, useId, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProjectsQuery } from '../shared/api/hooks';
import { formatDateTime } from '../shared/lib/format';
import { STATUS_LABELS } from '../shared/lib/project';

type PageId = 'projects' | 'create' | 'brief' | 'research' | 'evidence' | 'users' | 'concepts' | 'scenario' | 'proposal';

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
  const projectsQuery = useProjectsQuery();
  const projects = projectsQuery.data ?? [];

  const [activePage, setActivePage] = useState<PageId>(initialPage);
  const [createStep, setCreateStep] = useState(1);
  const [question, setQuestion] = useState('我想知道 eufy 下一代家庭安防还能做什么。');
  const [market, setMarket] = useState('美国');
  const [home, setHome] = useState('独栋住宅');
  const [scope, setScope] = useState('可视门铃 / 摄像头');
  const [direction, setDirection] = useState('AI / 软件能力');

  const [activeInsight, setActiveInsight] = useState(0);
  const [activeConcept, setActiveConcept] = useState('context');

  const [scenarioCovered, setScenarioCovered] = useState(false);
  const [scenarioEarly, setScenarioEarly] = useState(false);
  const [scenarioPresent, setScenarioPresent] = useState(true);
  const [rainProb, setRainProb] = useState(87);

  const computedDecision = (() => {
    if (scenarioCovered) return { text: '不打扰', badge: '保持安静', tone: 'gray' as const, msTime: '—', msg: '包裹处于受遮挡区域，当前不需要提醒。' };
    if (scenarioEarly) return { text: '不打扰', badge: '保持安静', tone: 'gray' as const, msTime: '—', msg: '预计用户在降雨前到家，无需提醒。' };
    if (!scenarioPresent) return { text: '不打扰', badge: '无提醒', tone: 'green' as const, msTime: '—', msg: '包裹已不在门外，无需提醒。' };
    if (rainProb < 40) return { text: '不打扰', badge: '低风险', tone: 'green' as const, msTime: '—', msg: '降雨概率过低，暂不提醒。' };
    if (rainProb < 70) return { text: '可监控', badge: '观望中', tone: 'purple' as const, msTime: '16:00', msg: '降雨概率中等，建议关注后续变化。' };
    return { text: '提醒', badge: '建议采取行动', tone: 'orange' as const, msTime: '16:00', msg: '预计下午 5 点左右开始下雨，你的包裹目前仍在门外。建议在天气变化前尽快取回。' };
  })();

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

  const latestProject = [...projects].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0];

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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
              <div className="demo-project-card">
                <div className="eyebrow">当前项目</div>
                <h3>eufy 情境感知家庭安防</h3>
                <div className="meta">
                  <span>阶段：场景验证</span><span>进度：78%</span><span>最近更新：今天</span>
                </div>
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('brief')}>继续研究</button>
                </div>
              </div>
              {latestProject ? (
                <div className="demo-project-card">
                  <div className="eyebrow">
                    {latestProject.status === 'researching' || latestProject.status === 'supplementing_research' ? '当前项目' : '历史项目'}
                  </div>
                  <h3 style={{ fontSize: 15, margin: '6px 0' }}>{latestProject.brief.category}</h3>
                  <div className="meta">
                    <span>{STATUS_LABELS[latestProject.status]}</span>
                    <span>进度：{latestProject.progress}%</span>
                    <span>最近更新：{formatDateTime(latestProject.updated_at)}</span>
                  </div>
                  <div className="demo-actions">
                    <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('research')}>继续研究</button>
                  </div>
                </div>
              ) : (
                <div className="demo-project-card">
                  <div className="eyebrow">历史项目</div>
                  <h3 style={{ fontSize: 15, margin: '6px 0' }}>eufy 租房安防机会研究</h3>
                  <div className="meta">
                    <span>阶段：证据采集</span><span>进度：46%</span><span>最近更新：2 天前</span>
                  </div>
                  <div className="demo-actions">
                    <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('research')}>继续研究</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Section: create ── */}
      <section className={`demo-page-section${activePage === 'create' ? ' active' : ''}`} id="create">
        <div className="demo-panel">
          <div className="demo-panel-head">
            <div>
              <div className="demo-panel-title">新建产品研究</div>
              <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>步骤 {createStep} / 3</div>
            </div>
            <span className={`demo-status demo-status--${createStep === 1 ? 'purple' : createStep === 2 ? 'purple' : 'green'}`}>
步骤 {createStep}/3
            </span>
          </div>
          <div style={{ padding: 18 }}>
            {createStep === 1 && (
              <div>
                <h2 style={{ fontSize: 20, margin: '6px 0 8px' }}>你今天想研究什么产品机会？</h2>
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
                <div className="eyebrow">AI 澄清</div>
                <h2 style={{ fontSize: 20, margin: '6px 0 8px' }}>确认研究边界</h2>
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
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--ghost" onClick={() => setCreateStep(1)}>返回</button>
                  <button className="demo-btn demo-btn--primary" onClick={() => setCreateStep(3)}>下一步</button>
                </div>
              </div>
            )}

            {createStep === 3 && (
              <div>
                <div className="eyebrow">研究 Brief 确认</div>
                <h2 style={{ fontSize: 20, margin: '6px 0 8px' }}>确认研究 Brief</h2>
                <div className="demo-panel" style={{ boxShadow: 'none', marginTop: 14 }}>
                  <div style={{ padding: 16 }}>
                    <div className="demo-fields">
                      <div className="demo-field"><small>项目名称</small><b>eufy 下一代情境感知家庭安防研究</b></div>
                      <div className="demo-field"><small>地区</small><b>{market}</b></div>
                      <div className="demo-field"><small>住宅类型</small><b>{home}</b></div>
                      <div className="demo-field"><small>产品范围</small><b>{scope}</b></div>
                    </div>
                    <div className="demo-field" style={{ marginTop: 10 }}>
                      <small>核心研究问题</small>
                      <b style={{ fontSize: 12, lineHeight: 1.6 }}>
                        在家庭安防中，有哪些场景是设备已经正确检测到了事件，但由于缺乏上下文理解，仍然没能帮助用户及时作出正确行动？
                      </b>
                    </div>
                    <div className="demo-field" style={{ marginTop: 10 }}>
                      <small>重点验证</small>
                      <b style={{ fontSize: 11, lineHeight: 1.8 }}>
                        ✓ 单一事件是否不足以完成判断<br />
                        ✓ 外部天气是否能提升提醒价值<br />
                        ✓ 家庭在家状态是否改变提醒决策<br />
                        ✓ 用户是否接受主动预测与提前干预<br />
                        ✓ 什么情况下 AI 应该保持安静
                      </b>
                    </div>
                  </div>
                </div>
                <div className="demo-actions">
                  <button className="demo-btn demo-btn--ghost" onClick={() => setCreateStep(2)}>修改研究范围</button>
                  <button className="demo-btn demo-btn--accent" onClick={() => jumpTo('brief')}>开始 AI 调研</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Section: brief ── */}
      <section className={`demo-page-section${activePage === 'brief' ? ' active' : ''}`} id="brief">
        <div className="demo-metrics">
          <div className="demo-metric"><small>研究市场</small><b>北美</b><span>美国优先</span></div>
          <div className="demo-metric"><small>核心方向</small><b>Level 4</b><span>情境感知主动安防</span></div>
          <div className="demo-metric"><small>核心场景</small><b>包裹</b><span>天气 × 无人在家</span></div>
          <div className="demo-metric"><small>当前阶段</small><b style={{ fontSize: 17 }}>场景验证</b><span>验证产品价值</span></div>
        </div>
        <div className="demo-grid2">
          <div className="demo-panel" style={{ padding: 18 }}>
            <div className="eyebrow" style={{ color: 'var(--accent)', fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>研究简报</div>
            <h2 style={{ fontSize: '1.25rem', margin: '4px 0 14px' }}>eufy 能否从"事件检测"升级为"场景理解"？</h2>
            <div className="demo-fields" style={{ marginTop: 0 }}>
              <div className="demo-field"><small>品类</small><b>可视门铃 / 摄像头</b></div>
              <div className="demo-field"><small>目标住宅</small><b>北美独栋住宅</b></div>
              <div className="demo-field"><small>创新路径</small><b>上下文 → 场景 → 未来状态 → 主动行动</b></div>
              <div className="demo-field"><small>首个验证场景</small><b>包裹 × 天气 × 家庭状态</b></div>
              <div className="demo-field"><small>核心风险</small><b>误提醒 / 过度打扰 / 隐私</b></div>
              <div className="demo-field"><small>核心原则</small><b>不是提醒更多，而是理解更深</b></div>
            </div>
            <div className="demo-actions">
              <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('research')}>继续进入实时调研</button>
              <button className="demo-btn demo-btn--ghost" onClick={() => jumpTo('scenario')}>直接查看 Level 4 演示</button>
            </div>
          </div>
          <div className="demo-panel">
            <div className="demo-panel-head">
              <div className="demo-panel-title">AI 原生工作流</div>
            </div>
            <div className="demo-step-list">
              <div className="demo-step done"><div className="num">1</div><div><strong>定义问题</strong><span>明确研究范围</span></div><span>已完成</span></div>
              <div className="demo-step done"><div className="num">2</div><div><strong>收集证据</strong><span>用户 / 竞品 / 技术</span></div><span>已完成</span></div>
              <div className="demo-step done"><div className="num">3</div><div><strong>用户替身挑战</strong><span>不同用户角色</span></div><span>已完成</span></div>
              <div className="demo-step done"><div className="num">4</div><div><strong>概念竞争</strong><span>专家 + 红队</span></div><span>已完成</span></div>
              <div className="demo-step current"><div className="num">5</div><div><strong>Level 4 场景验证</strong><span>反事实测试</span></div><span>当前</span></div>
              <div className="demo-step"><div className="num">6</div><div><strong>形成产品定义</strong><span>最终提案</span></div><span>待进行</span></div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Section: research ── */}
      <section className={`demo-page-section${activePage === 'research' ? ' active' : ''}`} id="research">
        <div className="demo-metrics">
          <div className="demo-metric"><small>研究进度</small><b>78%</b><span>2 轮调研</span></div>
          <div className="demo-metric"><small>来源</small><b>31</b><span>6 个独立域名</span></div>
          <div className="demo-metric"><small>有效证据</small><b>184</b><span>去重后</span></div>
          <div className="demo-metric"><small>反方证据</small><b>27</b><span>主动保留</span></div>
        </div>
        <div className="demo-research">
          <div className="demo-panel">
            <div className="demo-panel-head">
              <div className="demo-panel-title">调研流程</div>
              <span className="demo-status demo-status--green">进行中</span>
            </div>
            <div className="demo-pipeline">
              <div className="demo-pipe"><b>用户研究</b><div className="demo-bar"><span style={{ width: '100%' }} /></div><span className="demo-status demo-status--green">64 条</span></div>
              <div className="demo-pipe"><b>竞品研究</b><div className="demo-bar"><span style={{ width: '100%' }} /></div><span className="demo-status demo-status--green">52 条</span></div>
              <div className="demo-pipe"><b>技术可行性</b><div className="demo-bar"><span style={{ width: '82%' }} /></div><span className="demo-status demo-status--purple">82%</span></div>
              <div className="demo-pipe"><b>商业分析</b><div className="demo-bar"><span style={{ width: '74%' }} /></div><span className="demo-status demo-status--purple">74%</span></div>
              <div className="demo-pipe"><b>红队挑战</b><div className="demo-bar"><span style={{ width: '35%' }} /></div><span className="demo-status demo-status--gray">等待中</span></div>
            </div>
          </div>
          <div className="demo-panel">
            <div className="demo-panel-head">
              <div className="demo-panel-title">实时动态</div>
            </div>
            <div className="demo-activity">
              <div className="demo-event"><b>用户研究</b>发现：用户缺少的可能不是"更多提醒"，而是"真正需要行动时才出现的提醒"。</div>
              <div className="demo-event"><b>竞品研究</b>现有产品更多停留在事件检测、识别和通知。</div>
              <div className="demo-event"><b>技术分析</b>天气、时间、设备状态易获得；家庭在家状态和日历涉及权限与隐私。</div>
              <div className="demo-event"><b>证据采集</b>正在合并重复来源，并保留支持与反对材料。</div>
            </div>
            <div style={{ padding: '0 14px 14px' }}>
              <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('evidence')}>打开证据中心</button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Section: evidence ── */}
      <section className={`demo-page-section${activePage === 'evidence' ? ' active' : ''}`} id="evidence">
        <div className="demo-evidence-layout">
          <div className="demo-panel">
            <div className="demo-panel-head">
              <div className="demo-panel-title">机会洞察</div>
            </div>
            <div className="demo-insights">
              {[
                { strong: '提醒缺少上下文', span: '用户缺少的不是更多提醒，而是更有行动价值的提醒。' },
                { strong: '未来环境改变包裹风险', span: '包裹事件本身不足够，天气、家庭状态和时间会改变用户行动。' },
                { strong: '主动型 AI 必须知道什么时候安静', span: '高级 Agent 需要降低无意义干预，而不是把所有预测都变成通知。' },
              ].map((item, i) => (
                <button key={i} className={`demo-insight${activeInsight === i ? ' active' : ''}`} onClick={() => setActiveInsight(i)}>
                  <strong>{item.strong}</strong>
                  <span>{item.span}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="demo-panel demo-claim">
            <div className="eyebrow" style={{ color: 'var(--accent)' }}>关键结论</div>
            <h2>真正的价值缺口不在"有没有检测到事件"，而在"是否能结合上下文，在正确的时间提醒"。</h2>
            <div className="meta">
              <span>高置信度</span><span>42 条证据</span><span>6 个来源</span><span>8 条反方证据</span>
            </div>
            <blockquote>"我已经知道包裹在那里了，真正重要的是我现在是否需要采取行动。"</blockquote>
            <blockquote style={{ borderLeftColor: '#e7b3b3', background: '#fffafa' }}>反方观点：部分用户更偏好简单事件通知，并不希望系统处理更多上下文。</blockquote>
          </div>
        </div>
        <div className="demo-actions">
          <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('users')}>进入 AI 用户替身挑战</button>
        </div>
      </section>

      {/* ── Section: users ── */}
      <section className={`demo-page-section${activePage === 'users' ? ' active' : ''}`} id="users">
        <div className="demo-personas">
          {[
            { avatar: 'M', name: 'Maya · 独居用户', desc: '白天经常不在家，高频收包裹，不喜欢重复通知。', quote: '"如果能在问题发生前提醒我，那才真的有用。"', ground: '由 23 条评论、5 个社区讨论支撑' },
            { avatar: 'C', name: 'Chris · 家庭用户', desc: '重视多人共用、解释性，以及系统用了哪些家庭状态。', quote: '"我可以接受系统理解上下文，但我要知道它用了什么数据。"', ground: '由 31 条评论、4 份调查支撑' },
            { avatar: 'E', name: 'Emily · 高频收货用户', desc: '关注包裹安全，认为天气只有在改变行动时才有价值。', quote: '"天气本身不是功能，真正有价值的是它让我知道现在该不该做什么。"', ground: '由 40 条评论、6 个问答讨论支撑' },
          ].map((p) => (
            <div className="demo-persona" key={p.avatar}>
              <div className="demo-avatar">{p.avatar}</div>
              <h3>{p.name}</h3>
              <p>{p.desc}</p>
              <blockquote>{p.quote}</blockquote>
              <div className="ground">{p.ground}</div>
            </div>
          ))}
        </div>
        <div className="demo-actions">
          <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('concepts')}>进入概念竞技场</button>
        </div>
      </section>

      {/* ── Section: concepts ── */}
      <section className={`demo-page-section${activePage === 'concepts' ? ' active' : ''}`} id="concepts">
        <div className="demo-arena">
          <div className="demo-panel">
            <div className="demo-panel-head">
              <div className="demo-panel-title">概念竞技场</div>
              <span className="demo-status demo-status--purple">人工评审</span>
            </div>
            <div className="demo-concept-list">
              {[
                { id: 'context', name: 'eufy 情境智能 AI', desc: '跨上下文理解场景，预测未来风险，并在合适时机主动介入。', status: 'green', statusText: '领先方案', score: '8.7', bars: ['90%', '86%', '81%', '83%', '92%'] },
                { id: 'weather', name: '天气感知可视门铃', desc: '包裹识别后结合天气信息，在风险发生前提醒用户。', status: 'purple', statusText: 'MVP 场景', score: '7.2', bars: ['82%', '64%', '90%', '70%', '60%'] },
                { id: 'move', name: '搬家模式', desc: '设备、规则和家庭设置一键迁移到新住所。', status: 'red', statusText: '已淘汰', score: '6.5', bars: ['65%', '55%', '90%', '62%', '54%'], rejected: true },
              ].map((c) => (
                <button key={c.id} className={`demo-concept-btn${activeConcept === c.id ? ' active' : ''}${c.rejected ? ' rejected' : ''}`} onClick={() => setActiveConcept(c.id)}>
                  <div className="demo-concept-top">
                    <div>
                      <h3>{c.name}</h3>
                      <p>{c.desc}</p>
                    </div>
                    <span className={`demo-status demo-status--${c.status}`}>{c.statusText}</span>
                  </div>
                  <div className="demo-scoreline">
                    <div className="demo-score">{c.score}</div>
                    <div className="demo-mini-bars">
                      {c.bars.map((w, i) => (<div className="demo-mini" key={i}><span style={{ width: w }} /></div>))}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div className="demo-panel demo-concept-detail">
            <div className="eyebrow" style={{ color: 'var(--accent)' }}>领先方案</div>
            <h2 style={{ fontSize: 18, margin: '4px 0' }}>eufy 情境智能 AI</h2>
            <div style={{ marginTop: 12 }}>
              {[
                { label: '用户价值', w: '90%', score: '9.0' },
                { label: '创新性', w: '86%', score: '8.6' },
                { label: '可行性', w: '81%', score: '8.1' },
                { label: '商业价值', w: '83%', score: '8.3' },
                { label: '证据强度', w: '92%', score: '9.2' },
              ].map((r) => (
                <div className="demo-score-row" key={r.label}>
                  <span>{r.label}</span>
                  <div className="demo-bar"><span style={{ width: r.w }} /></div>
                  <b>{r.score}</b>
                </div>
              ))}
            </div>
            <div className="demo-panel-title" style={{ marginTop: 14 }}>为什么做 / 为什么不做</div>
            <div className="demo-reason"><i>✓</i><div>平台级能力，可覆盖包裹、访客、车辆、家庭状态等多类场景。</div></div>
            <div className="demo-reason"><i>✓</i><div>创新集中在上下文、场景理解和未来预测层，而不是单一功能。</div></div>
            <div className="demo-reason warn"><i>!</i><div>主要风险是误干预、隐私授权和可解释性。</div></div>
          </div>
        </div>
        <div className="demo-actions">
          <button className="demo-btn demo-btn--primary" onClick={() => jumpTo('scenario')}>将优胜概念送入场景智能实验室</button>
        </div>
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
