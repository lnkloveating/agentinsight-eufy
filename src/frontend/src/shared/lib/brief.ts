import type { BackendResearchBrief, ResearchBrief } from '../types/api';

function cleanList(values: Array<string | undefined>, fallback: string[]): string[] {
  const normalized = values.map((value) => value?.trim()).filter((value): value is string => Boolean(value));
  return Array.from(new Set(normalized.length > 0 ? normalized : fallback));
}

export function buildHomeSafetyBrief(input: {
  question?: string;
  targetEcosystem?: string;
  comparisonEcosystems?: string[];
  targetUsers?: string[];
  markets?: string[];
  riskScenarios?: string[];
  safetyGoals?: string[];
  evaluationDimensions?: string[];
  validationExpectations?: string[];
  externalConstraints?: string[];
}): BackendResearchBrief {
  const targetEcosystems = cleanList([input.targetEcosystem], ['eufy 家庭安防生态']);
  const riskScenarios = cleanList(input.riskScenarios ?? [], ['门口包裹暴露', '夜间误报', '离家期间异常事件']);
  const evaluationDimensions = cleanList(input.evaluationDimensions ?? [], ['用户价值', '安全边界', '设备能力缺口', '竞品差异化']);
  const safetyGoals = cleanList(input.safetyGoals ?? [], ['提前识别家庭安全风险', '减少误报和过度打扰', '保留可复核证据边界']);

  return {
    question: input.question?.trim() || 'eufy 家庭安防生态在 AI 原生场景下还有哪些可验证的产品机会？',
    research_scope: 'home_safety_ecosystem',
    safety_domains: ['general_home_safety', 'property_security', 'perimeter_safety'],
    target_ecosystems: targetEcosystems,
    comparison_ecosystems: cleanList(input.comparisonEcosystems ?? [], ['Ring', 'Google Nest', 'Arlo']),
    target_users: cleanList(input.targetUsers ?? [], ['北美家庭安防用户']),
    markets: cleanList(input.markets ?? [], ['美国']),
    time_horizon: '未来 6-12 个月',
    safety_goals: safetyGoals,
    risk_scenarios: riskScenarios,
    authorized_signal_types: [
      'visual_event_metadata',
      'motion_event',
      'door_event',
      'device_status',
      'household_presence',
      'environment_context',
      'user_confirmation',
    ],
    privacy_boundary: {
      raw_media_allowed: false,
      restricted_zones: ['卧室', '浴室', '儿童私人空间'],
      retention_policy: '仅保留研究所需的摘要、片段和可复核引用；不扩散原始家庭媒体。',
      external_sharing_allowed: false,
    },
    intervention_boundary: {
      allowed_interventions: [
        'continue_observing',
        'request_additional_signal',
        'local_prompt',
        'ask_user',
        'preserve_evidence',
      ],
      prohibited_actions: [
        '自动报警',
        '自动联系执法机构',
        '推断敏感身份或健康状态',
        ...(input.externalConstraints ?? []),
      ],
      high_impact_action_requires_human_approval: true,
    },
    forbidden_inferences: ['人脸身份识别', '健康状态推断', '受保护属性推断', '未经授权的室内活动判断'],
    evaluation_dimensions: evaluationDimensions,
    validation_expectations: cleanList(input.validationExpectations ?? [], [
      '所有机会必须引用真实资料或明确标记 unknown',
      '区分设备能力、用户需求和竞品事实',
      '高影响动作必须保留人工审批',
    ]),
    source_permissions: {
      public_sources: true,
      user_uploaded_materials: true,
      enterprise_internal_materials: false,
      authorized_household_events: false,
    },
    deliverables: ['ecosystem_opportunity_portfolio', 'device_capability_gap', 'pilot_recommendation'],
  };
}

export function toDisplayBrief(brief: BackendResearchBrief): ResearchBrief {
  return {
    ...brief,
    category: brief.target_ecosystems.join(' / '),
    target_user: brief.target_users.join(' / '),
    region: brief.markets.join(' / '),
    scenarios: brief.risk_scenarios,
    constraints: [
      brief.privacy_boundary.raw_media_allowed ? '允许原始媒体' : '不使用原始媒体',
      brief.privacy_boundary.external_sharing_allowed ? '允许外部共享' : '禁止外部共享',
      ...brief.privacy_boundary.restricted_zones.map((zone) => `限制区域：${zone}`),
      ...brief.intervention_boundary.prohibited_actions.map((action) => `禁止：${action}`),
    ],
    focus_dimensions: brief.evaluation_dimensions,
  };
}

export function buildHomeSafetyDisplayBrief(input: Parameters<typeof buildHomeSafetyBrief>[0]): ResearchBrief {
  return toDisplayBrief(buildHomeSafetyBrief(input));
}
