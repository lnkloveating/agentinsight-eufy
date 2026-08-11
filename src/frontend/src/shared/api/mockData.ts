import type {
  AgentRun,
  Claim,
  Concept,
  DecisionAction,
  DecisionCreateInput,
  Evidence,
  EvidencePage,
  Metrics,
  PendingDecision,
  Project,
  ProjectCreateInput,
  ProjectEvent,
  ProjectStatus,
  Report,
  WorkspaceData,
} from '../types/api';
import { toDisplayBrief } from '../lib/brief';

const STORAGE_KEY = 'agentinsight-eufy-mock-db';

interface MockDatabase {
  projects: Project[];
  agentRuns: Record<string, AgentRun[]>;
  evidence: Record<string, EvidencePage>;
  claims: Record<string, Claim[]>;
  concepts: Record<string, Concept[]>;
  reports: Record<string, Report>;
  metrics: Record<string, Metrics>;
  events: Record<string, ProjectEvent[]>;
}

function nowIso(offsetMinutes = 0): string {
  return new Date(Date.now() + offsetMinutes * 60_000).toISOString();
}

function makePendingDecision(gate: string, allowed_actions: DecisionAction[]): PendingDecision {
  return {
    decision_id: `decision_${gate}_${Math.random().toString(36).slice(2, 8)}`,
    gate,
    allowed_actions,
  };
}

function seedDatabase(): MockDatabase {
  const project: Project = {
    project_id: 'proj_eufy_renters',
    status: 'awaiting_concept_approval',
    current_stage: 'concept_synthesis',
    progress: 64,
    brief: {
      question: 'eufy 是否应该为北美租房用户设计一套低安装门槛、可迁移、低订阅依赖的家庭安防方案？',
      category: '家庭安防',
      target_user: '北美租房家庭与合租用户',
      region: '美国 / 加拿大',
      scenarios: ['门口访客', '搬家迁移', '室友共享空间', '离家看护'],
      constraints: ['免打孔', '低订阅依赖', '本地隐私优先', '弱网可用'],
      focus_dimensions: ['安装难度', '迁移成本', '证据留存', '权限边界'],
    },
    pending_decision: makePendingDecision('concept', ['approve', 'research_more', 'reject']),
    created_at: nowIso(-600),
    updated_at: nowIso(-5),
  };

  const evidenceItems: Evidence[] = [
    {
      evidence_id: 'ev_safehome_001',
      source_url: 'https://www.safehome.org/security-cameras/stats/',
      source_type: 'survey',
      title: 'SafeHome 2026 家庭安防调查',
      excerpt: '租房用户更看重安装简易性、月费成本与存储方式灵活性。',
      captured_at: nowIso(-360),
      status: 'verified',
      content_hash: 'hash_safehome_001',
      confidence: 0.89,
    },
    {
      evidence_id: 'ev_review_002',
      source_url: 'https://example.com/eufy-review-thread',
      source_type: 'community',
      title: 'eufy 用户对搬家迁移的反馈',
      excerpt: '用户在迁居时希望继承设备权限和历史事件，而不是重新配置。',
      captured_at: nowIso(-220),
      status: 'verified',
      content_hash: 'hash_review_002',
      confidence: 0.76,
    },
    {
      evidence_id: 'ev_failed_003',
      source_url: 'https://example.com/missed-source',
      source_type: 'retail',
      title: '北美零售渠道订阅信息抓取失败',
      excerpt: '该来源因反爬限制未完成采集，仍计入覆盖率缺口。',
      captured_at: nowIso(-140),
      status: 'failed',
      content_hash: 'hash_failed_003',
      confidence: 0.12,
    },
  ];

  const concepts: Concept[] = [
    {
      concept_id: 'concept_portable_hub',
      name: 'Portable Privacy Hub',
      target_user: '需要频繁搬家的租房家庭',
      value_proposition: '把摄像头、存储和家庭成员权限打包成可迁移的一体化安防套件。',
      supporting_evidence_ids: ['ev_safehome_001', 'ev_review_002'],
      risks: ['初始硬件成本可能偏高', '迁移流程必须足够傻瓜化'],
      red_team_findings: ['如果安装仍依赖复杂校准，价值会快速减弱。'],
      scores: { desirability: 8.7, feasibility: 7.1, differentiation: 8.2 },
      status: 'candidate',
    },
    {
      concept_id: 'concept_shared_boundary',
      name: 'Shared Boundary Mode',
      target_user: '多室友共享空间用户',
      value_proposition: '用分角色权限和隐私遮罩处理室友、房东与访客的边界冲突。',
      supporting_evidence_ids: ['ev_review_002'],
      risks: ['需验证用户是否愿意为软件能力单独付费'],
      red_team_findings: ['证据仍偏定性，缺少足够广泛的量化支撑。'],
      scores: { desirability: 7.9, feasibility: 8.3, differentiation: 7.4 },
      status: 'candidate',
    },
    {
      concept_id: 'concept_subscription_bundle',
      name: 'Subscription Saver Bundle',
      target_user: '价格敏感用户',
      value_proposition: '通过一次性硬件溢价替代长期订阅。',
      supporting_evidence_ids: [],
      risks: ['价值主张容易被现有产品线覆盖'],
      red_team_findings: ['缺少有效证据支持，不应晋级。'],
      scores: { desirability: 5.2, feasibility: 8.8, differentiation: 4.6 },
      status: 'rejected',
    },
  ];

  const claims: Claim[] = [
    {
      claim_id: 'claim_installation',
      statement: '安装限制与搬家迁移是租房用户采用家庭安防的核心阻力。',
      evidence_ids: ['ev_safehome_001', 'ev_review_002'],
      contradicting_evidence_ids: [],
      status: 'supported',
    },
    {
      claim_id: 'claim_subscription',
      statement: '用户愿意为免订阅的方案支付显著硬件溢价。',
      evidence_ids: [],
      contradicting_evidence_ids: ['ev_failed_003'],
      status: 'missing_evidence',
    },
  ];

  const report: Report = {
    report_id: 'report_eufy_v1',
    project_id: project.project_id,
    version: 1,
    recommendation: '优先推进 Portable Privacy Hub，并将 Shared Boundary Mode 作为软件能力包并行验证。',
    sections: {
      target_users: ['北美租房家庭', '多室友合租用户'],
      problem_severity: '安装、迁移和权限边界构成了比“单纯识别更准”更真实的差异化机会。',
      concept: 'Portable Privacy Hub',
      feature_to_evidence_mapping: [
        '免打孔安装 <- ev_safehome_001',
        '搬家迁移继承 <- ev_review_002',
      ],
      limitations: ['渠道订阅数据采集失败，价格假设仍需补证。'],
    },
    cited_evidence_ids: ['ev_safehome_001', 'ev_review_002'],
    unknowns: ['目标用户可接受的硬件溢价区间', '权限模式对房东场景的真实吸引力'],
    generated_at: nowIso(-25),
  };

  const metrics: Metrics = {
    elapsed_seconds: 14_820,
    valid_evidence_count: 2,
    citation_coverage: 0.84,
    source_diversity: 3,
    estimated_cost: 61.3,
    comparison: {
      ai_assisted_hours: 4.1,
      traditional_hours: 18.5,
      traceability_score: 0.92,
      blind_review_score: 8.1,
    },
  };

  const agentRuns: AgentRun[] = [
    {
      agent_run_id: 'agent_manager',
      project_id: project.project_id,
      agent_type: 'manager',
      agent_name: '调研总管 Agent',
      status: 'waiting',
      progress: 66,
      message: '候选概念已生成，等待人工晋级决策。',
      started_at: nowIso(-520),
      completed_at: null,
    },
    {
      agent_run_id: 'agent_user',
      project_id: project.project_id,
      agent_type: 'user_research',
      agent_name: '用户研究 Agent',
      status: 'completed',
      progress: 100,
      message: '用户痛点与场景聚类已完成。',
      started_at: nowIso(-500),
      completed_at: nowIso(-150),
    },
    {
      agent_run_id: 'agent_competitor',
      project_id: project.project_id,
      agent_type: 'competitor',
      agent_name: '竞品 Agent',
      status: 'completed',
      progress: 100,
      message: '竞品能力与订阅差异矩阵已完成。',
      started_at: nowIso(-480),
      completed_at: nowIso(-170),
    },
    {
      agent_run_id: 'agent_red_team',
      project_id: project.project_id,
      agent_type: 'red_team',
      agent_name: '红队 Agent',
      status: 'waiting',
      progress: 58,
      message: '等待概念晋级后继续挑战与查漏。',
      started_at: nowIso(-120),
      completed_at: null,
    },
  ];

  const events: ProjectEvent[] = [
    {
      event_id: 'evt_001',
      event_type: 'project_created',
      project_id: project.project_id,
      sequence_number: 1,
      timestamp: nowIso(-600),
      data: { actor: '产品经理' },
      trace_id: 'trace_evt_001',
    },
    {
      event_id: 'evt_002',
      event_type: 'research_started',
      project_id: project.project_id,
      sequence_number: 2,
      timestamp: nowIso(-520),
      data: { stage: 'research_planning' },
      trace_id: 'trace_evt_002',
    },
    {
      event_id: 'evt_003',
      event_type: 'evidence_collected',
      project_id: project.project_id,
      sequence_number: 3,
      timestamp: nowIso(-360),
      data: { evidence_id: 'ev_safehome_001' },
      trace_id: 'trace_evt_003',
    },
    {
      event_id: 'evt_004',
      event_type: 'evidence_failed',
      project_id: project.project_id,
      sequence_number: 4,
      timestamp: nowIso(-140),
      data: { source: 'retail-pricing' },
      trace_id: 'trace_evt_004',
    },
    {
      event_id: 'evt_005',
      event_type: 'concept_generated',
      project_id: project.project_id,
      sequence_number: 5,
      timestamp: nowIso(-40),
      data: { count: 3 },
      trace_id: 'trace_evt_005',
    },
    {
      event_id: 'evt_006',
      event_type: 'decision_requested',
      project_id: project.project_id,
      sequence_number: 6,
      timestamp: nowIso(-5),
      data: { gate: 'concept' },
      trace_id: 'trace_evt_006',
    },
  ];

  return {
    projects: [project],
    agentRuns: { [project.project_id]: agentRuns },
    evidence: { [project.project_id]: { items: evidenceItems, next_cursor: null, total: evidenceItems.length } },
    claims: { [project.project_id]: claims },
    concepts: { [project.project_id]: concepts },
    reports: { [project.project_id]: report },
    metrics: { [project.project_id]: metrics },
    events: { [project.project_id]: events },
  };
}

function readStorage(): MockDatabase {
  if (typeof window === 'undefined') {
    return seedDatabase();
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    const initial = seedDatabase();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
    return initial;
  }

  try {
    return JSON.parse(raw) as MockDatabase;
  } catch {
    const initial = seedDatabase();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
    return initial;
  }
}

function writeStorage(database: MockDatabase): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(database));
  }
}

let databaseCache: MockDatabase | null = null;

function getDatabase(): MockDatabase {
  if (!databaseCache) {
    databaseCache = readStorage();
  }
  return databaseCache;
}

function commitDatabase(nextDatabase: MockDatabase): MockDatabase {
  databaseCache = nextDatabase;
  writeStorage(nextDatabase);
  return nextDatabase;
}

function cloneDatabase(): MockDatabase {
  return JSON.parse(JSON.stringify(getDatabase())) as MockDatabase;
}

function appendEvent(database: MockDatabase, project_id: string, event_type: string, data: Record<string, unknown>): void {
  const projectEvents = database.events[project_id] ?? [];
  const sequence = projectEvents.length + 1;
  projectEvents.push({
    event_id: `evt_${project_id}_${sequence}`,
    event_type,
    project_id,
    sequence_number: sequence,
    timestamp: new Date().toISOString(),
    data,
    trace_id: `trace_${project_id}_${sequence}`,
  });
  database.events[project_id] = projectEvents;
}

function updateProjectStatus(
  project: Project,
  nextStatus: ProjectStatus,
  currentStage: string,
  pendingDecision: PendingDecision | null,
  progress: number,
): Project {
  return {
    ...project,
    status: nextStatus,
    current_stage: currentStage,
    pending_decision: pendingDecision,
    progress,
    updated_at: new Date().toISOString(),
  };
}

export const mockApi = {
  listProjects(): Project[] {
    return getDatabase().projects;
  },

  createProject(input: ProjectCreateInput): Project {
    const database = cloneDatabase();
    const project_id = `proj_${Math.random().toString(36).slice(2, 8)}`;
    const project: Project = {
      project_id,
      status: 'awaiting_brief_approval',
      current_stage: 'brief_confirmation',
      progress: 8,
      brief: toDisplayBrief(input.brief),
      pending_decision: makePendingDecision('brief', ['approve', 'terminate']),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    database.projects = [project, ...database.projects];
    database.agentRuns[project_id] = [
      {
        agent_run_id: `agent_${project_id}_manager`,
        project_id,
        agent_type: 'manager',
        agent_name: '调研总管 Agent',
        status: 'waiting',
        progress: 0,
        message: '等待 Brief 确认后开始规划调研任务。',
        started_at: null,
        completed_at: null,
      },
    ];
    database.evidence[project_id] = { items: [], next_cursor: null, total: 0 };
    database.claims[project_id] = [];
    database.concepts[project_id] = [];
    database.events[project_id] = [];
    appendEvent(database, project_id, 'project_created', { actor: 'frontend' });

    commitDatabase(database);
    return project;
  },

  getProject(project_id: string): Project {
    const project = getDatabase().projects.find((item) => item.project_id === project_id);
    if (!project) {
      throw new Error('PROJECT_NOT_FOUND');
    }
    return project;
  },

  listAgentRuns(project_id: string): AgentRun[] {
    return getDatabase().agentRuns[project_id] ?? [];
  },

  listEvidence(project_id: string): EvidencePage {
    return getDatabase().evidence[project_id] ?? { items: [], next_cursor: null, total: 0 };
  },

  listClaims(project_id: string): Claim[] {
    return getDatabase().claims[project_id] ?? [];
  },

  listConcepts(project_id: string): Concept[] {
    return getDatabase().concepts[project_id] ?? [];
  },

  getReport(project_id: string): Report | null {
    return getDatabase().reports[project_id] ?? null;
  },

  getMetrics(project_id: string): Metrics | null {
    return getDatabase().metrics[project_id] ?? null;
  },

  listEvents(project_id: string): ProjectEvent[] {
    return getDatabase().events[project_id] ?? [];
  },

  submitDecision(project_id: string, input: DecisionCreateInput): Project {
    const database = cloneDatabase();
    const projectIndex = database.projects.findIndex((item) => item.project_id === project_id);
    if (projectIndex < 0) {
      throw new Error('PROJECT_NOT_FOUND');
    }

    const project = database.projects[projectIndex];
    if (project.pending_decision?.decision_id !== input.decision_id) {
      throw new Error('DECISION_ID_MISMATCH');
    }

    let nextProject = project;

    if (project.pending_decision?.gate === 'brief' && input.action === 'approve') {
      nextProject = updateProjectStatus(project, 'researching', 'research_planning', null, 24);

      const seededAgentRuns: AgentRun[] = [
        {
          agent_run_id: `agent_${project_id}_manager`,
          project_id,
          agent_type: 'manager',
          agent_name: '调研总管 Agent',
          status: 'completed',
          progress: 100,
          message: '调研规划完成，已派发子任务。',
          started_at: new Date(Date.now() - 120_000).toISOString(),
          completed_at: new Date().toISOString(),
        },
        {
          agent_run_id: `agent_${project_id}_user`,
          project_id,
          agent_type: 'user_research',
          agent_name: '用户研究 Agent',
          status: 'completed',
          progress: 100,
          message: '用户痛点与场景聚类完成。',
          started_at: new Date(Date.now() - 90_000).toISOString(),
          completed_at: new Date(Date.now() - 10_000).toISOString(),
        },
        {
          agent_run_id: `agent_${project_id}_competitor`,
          project_id,
          agent_type: 'competitor',
          agent_name: '竞品 Agent',
          status: 'completed',
          progress: 100,
          message: '竞品能力与差异矩阵已完成。',
          started_at: new Date(Date.now() - 80_000).toISOString(),
          completed_at: new Date(Date.now() - 5_000).toISOString(),
        },
        {
          agent_run_id: `agent_${project_id}_technical`,
          project_id,
          agent_type: 'technical',
          agent_name: '技术可行性 Agent',
          status: 'running',
          progress: 70,
          message: '技术栈评估进行中…',
          started_at: new Date(Date.now() - 60_000).toISOString(),
          completed_at: null,
        },
        {
          agent_run_id: `agent_${project_id}_business`,
          project_id,
          agent_type: 'business',
          agent_name: '商业分析 Agent',
          status: 'running',
          progress: 55,
          message: '市场规模与定价分析中…',
          started_at: new Date(Date.now() - 50_000).toISOString(),
          completed_at: null,
        },
        {
          agent_run_id: `agent_${project_id}_redteam`,
          project_id,
          agent_type: 'red_team',
          agent_name: '红队挑战 Agent',
          status: 'waiting',
          progress: 15,
          message: '等待概念生成后介入挑战。',
          started_at: new Date(Date.now() - 30_000).toISOString(),
          completed_at: null,
        },
      ];
      database.agentRuns[project_id] = seededAgentRuns;

      const seededEvidence: Evidence[] = [
        {
          evidence_id: `ev_${project_id}_001`,
          source_url: 'https://example.com/user-survey',
          source_type: 'survey',
          title: `${project.brief.target_user} 用户调研报告`,
          excerpt: `${project.brief.region}市场${project.brief.category}类产品中，${project.brief.scenarios[0] ?? '核心场景'}是用户提及频次最高的使用场景。`,
          captured_at: new Date(Date.now() - 80_000).toISOString(),
          status: 'verified',
          content_hash: `hash_${project_id}_001`,
          confidence: 0.82,
        },
        {
          evidence_id: `ev_${project_id}_002`,
          source_url: 'https://example.com/competitor-analysis',
          source_type: 'community',
          title: '竞品功能对比分析',
          excerpt: `当前竞品在${project.brief.focus_dimensions[0] ?? '核心维度'}上仍有明显缺口，用户期望更主动的智能体验。`,
          captured_at: new Date(Date.now() - 50_000).toISOString(),
          status: 'verified',
          content_hash: `hash_${project_id}_002`,
          confidence: 0.75,
        },
        {
          evidence_id: `ev_${project_id}_003`,
          source_url: 'https://example.com/tech-feasibility',
          source_type: 'retail',
          title: '技术实现可行性评估',
          excerpt: '当前技术栈可支持基础场景推理，但多维度上下文融合仍需额外研发投入。',
          captured_at: new Date(Date.now() - 20_000).toISOString(),
          status: 'pending',
          content_hash: `hash_${project_id}_003`,
          confidence: 0.68,
        },
      ];
      database.evidence[project_id] = { items: seededEvidence, next_cursor: null, total: seededEvidence.length };

      const seededClaims: Claim[] = [
        {
          claim_id: `claim_${project_id}_001`,
          statement: `${project.brief.scenarios[0] ?? '核心场景'}场景下用户对被动通知的满意度持续走低，期望系统更主动预判风险。`,
          evidence_ids: [`ev_${project_id}_001`],
          contradicting_evidence_ids: [],
          status: 'supported',
        },
        {
          claim_id: `claim_${project_id}_002`,
          statement: `${project.brief.focus_dimensions[0] ?? '关键能力'}的竞品覆盖度不足，存在明确差异化机会。`,
          evidence_ids: [`ev_${project_id}_002`],
          contradicting_evidence_ids: [],
          status: 'missing_evidence',
        },
      ];
      database.claims[project_id] = seededClaims;

      database.reports[project_id] = {
        report_id: `report_${project_id}_v1`,
        project_id,
        version: 1,
        recommendation: '待概念生成后生成最终提案。',
        sections: {},
        cited_evidence_ids: [],
        unknowns: [],
        generated_at: new Date().toISOString(),
      };

      database.metrics[project_id] = {
        elapsed_seconds: 8_400,
        valid_evidence_count: 2,
        citation_coverage: 0.45,
        source_diversity: 3,
        estimated_cost: 52.2,
        comparison: {},
      };

      nextProject = updateProjectStatus(nextProject, 'researching', 'research_planning', null, 46);

      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'brief' });
      appendEvent(database, project_id, 'research_started', { stage: 'research_planning' });
      appendEvent(database, project_id, 'evidence_collected', { evidence_id: seededEvidence[0].evidence_id });
      appendEvent(database, project_id, 'evidence_collected', { evidence_id: seededEvidence[1].evidence_id });
      appendEvent(database, project_id, 'research_finding', { message: `用户研究 Agent 发现：${seededClaims[0].statement}` });
      appendEvent(database, project_id, 'research_finding', { message: `竞品 Agent 发现：${seededClaims[1].statement}` });
    } else if (project.pending_decision?.gate === 'brief' && input.action === 'terminate') {
      nextProject = updateProjectStatus(project, 'terminated', 'brief_closed', null, 10);
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'brief' });
    } else if (project.pending_decision?.gate === 'concept' && input.action === 'approve') {
      nextProject = updateProjectStatus(
        project,
        'awaiting_final_approval',
        'final_review',
        makePendingDecision('final', ['approve', 'revise', 'terminate']),
        88,
      );
      if (database.reports[project_id]) {
        database.reports[project_id] = {
          ...database.reports[project_id],
          generated_at: new Date().toISOString(),
        };
      }
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'concept' });
      appendEvent(database, project_id, 'report_generated', { concept_ids: input.selected_concept_ids });
    } else if (project.pending_decision?.gate === 'concept' && input.action === 'research_more') {
      nextProject = updateProjectStatus(project, 'supplementing_research', 'supplemental_research', null, 70);
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'concept' });
    } else if (project.pending_decision?.gate === 'concept' && input.action === 'reject') {
      nextProject = updateProjectStatus(project, 'terminated', 'concept_rejected', null, project.progress);
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'concept' });
    } else if (project.pending_decision?.gate === 'final' && input.action === 'approve') {
      nextProject = updateProjectStatus(project, 'completed', 'completed', null, 100);
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'final' });
    } else if (project.pending_decision?.gate === 'final' && input.action === 'revise') {
      nextProject = updateProjectStatus(project, 'generating_report', 'report_revision', null, 82);
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'final' });
    } else if (project.pending_decision?.gate === 'final' && input.action === 'terminate') {
      nextProject = updateProjectStatus(project, 'terminated', 'final_closed', null, project.progress);
      appendEvent(database, project_id, 'decision_submitted', { action: input.action, gate: 'final' });
    }

    database.projects[projectIndex] = nextProject;
    commitDatabase(database);
    return nextProject;
  },

  deleteProject(project_id: string): void {
    const database = cloneDatabase();
    database.projects = database.projects.filter((item) => item.project_id !== project_id);
    delete database.agentRuns[project_id];
    delete database.evidence[project_id];
    delete database.claims[project_id];
    delete database.concepts[project_id];
    delete database.reports[project_id];
    delete database.metrics[project_id];
    delete database.events[project_id];
    commitDatabase(database);
  },

  startUserResearch(project_id: string): void {
    const database = cloneDatabase();
    const userAgent = database.agentRuns[project_id]?.find(
      (run) => run.agent_type === 'user_research',
    );
    if (userAgent) {
      userAgent.status = 'completed';
      userAgent.progress = 100;
      userAgent.completed_at = new Date().toISOString();
      userAgent.message = '用户痛点与场景聚类完成。';
    }
    const project = database.projects.find((p) => p.project_id === project_id);
    if (project) {
      project.progress = Math.max(project.progress, 50);
      project.updated_at = new Date().toISOString();
    }
    appendEvent(database, project_id, 'agent_completed', {
      agent_type: 'user_research',
      message: '用户研究 Agent 已完成调研。',
    });
    commitDatabase(database);
  },

  getWorkspace(project_id: string): WorkspaceData {
    return {
      project: this.getProject(project_id),
      agentRuns: this.listAgentRuns(project_id),
      evidencePage: this.listEvidence(project_id),
      claims: this.listClaims(project_id),
      concepts: this.listConcepts(project_id),
      report: this.getReport(project_id),
      metrics: this.getMetrics(project_id),
      events: this.listEvents(project_id),
    };
  },
};
