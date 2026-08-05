# AIPDF Agent 协作契约

## 1. 目的

本文定义六类 Agent 的职责、依赖、结构化输入输出、失败条件和返工规则。Agent 可以复用同一模型，但不得复用同一套通用 Prompt 冒充不同专家，也不得通过自由对话传递未经验证的事实。

所有 Agent 输出必须满足：

- 通过 Pydantic 或等价 JSON Schema 校验；
- 事实性字段关联有效 `evidence_ids`；
- 区分事实、用户观点、厂商声明、推断和未知项；
- 显式返回 `status`、`quality_score`、`unknowns` 和 `errors`；
- 不传播隐藏思维过程，只保存结构化依据、阶段摘要和决策理由。

## 2. 统一执行状态

Agent Task 状态：

```text
pending
running
completed
partial
failed
blocked
needs_revision
cancelled
```

Innovation 状态：

```text
draft
evidence_pending
tech_review
business_review
red_team_review
needs_revision
recommended
rejected
```

Evidence 状态：

```text
verified
partially_verified
unverified
outdated
mock
invalid
```

采集任务的 `queued/running/succeeded/partial/blocked/failed` 与 Evidence 状态分开保存。采集失败不是一条可支持 Claim 的 Evidence，但必须保留在覆盖率和 Trace 中。

## 3. 共享对象

### 3.1 ResearchTask

```json
{
  "task_id": "task_xxx",
  "project_id": "proj_xxx",
  "agent_type": "user_research",
  "goal": "从真实用户资料识别事件链和未满足需求",
  "scope": {},
  "required_artifacts": [],
  "evidence_rules": {
    "citation_required": true,
    "minimum_independent_domains": 2
  },
  "budget": {
    "max_pages": 50,
    "max_iterations": 2,
    "deadline_seconds": 600
  },
  "depends_on": [],
  "acceptance_checks": []
}
```

### 3.2 ResearchArtifact

```json
{
  "artifact_id": "artifact_xxx",
  "task_id": "task_xxx",
  "artifact_type": "user_research",
  "schema_version": "1.0",
  "status": "completed",
  "payload": {},
  "evidence_ids": [],
  "contradictions": [],
  "unknowns": [],
  "quality_score": 0,
  "errors": []
}
```

### 3.3 Innovation

```json
{
  "innovation_id": "inv_xxx",
  "name": "Package Risk Intelligence",
  "status": "red_team_review",
  "target_user": {
    "persona_ids": [],
    "description": ""
  },
  "problem": {
    "pain_ids": [],
    "description": ""
  },
  "event_understanding": {
    "base_event": {
      "type": "package_delivered",
      "source": "doorbell_camera"
    },
    "event_state": {
      "type": "package_still_present",
      "source": "camera"
    },
    "context_signals": [],
    "inference": "",
    "risk_or_value": "",
    "recommended_action": ""
  },
  "competitor_gap_ids": [],
  "technical_assessment": {},
  "business_assessment": {},
  "red_team_review": {},
  "evidence_ids": [],
  "score_breakdown": {},
  "final_score": 0
}
```

`context_signals` 至少包含两个元素；每个信号必须记录 `type`、`source`、`availability`、`authorization`、`freshness`、`latency`、`confidence` 和 `fallback`。

### 3.4 StageDecision

```json
{
  "decision_id": "decision_xxx",
  "project_id": "proj_xxx",
  "gate": "scenario",
  "action": "approve",
  "actor": {
    "type": "human",
    "open_id": "ou_xxx",
    "display_name": ""
  },
  "reason": "",
  "selected_innovation_ids": [],
  "affected_task_ids": [],
  "resume_checkpoint_id": "checkpoint_xxx",
  "created_at": "2026-08-06T00:00:00Z"
}
```

## 4. 六类 Agent

### 4.1 调研总管 Agent

职责：标准化目标、拆分任务、控制依赖和预算、执行质量检查、触发补研、整合最终结论。

必须读取：Research Brief、项目预算、Agent Artifact、Evidence 覆盖、红队结果和人工决定。

必须输出：

```json
{
  "normalized_scope": {},
  "task_plan": [],
  "agent_assignments": [],
  "quality_checks": [],
  "evidence_coverage": {},
  "recommended_innovation_ids": [],
  "rejected_innovation_ids": [],
  "open_questions": [],
  "final_recommendation": "investigate"
}
```

禁止：在专业 Agent 尚未完成时直接生成完整结论；用语言补齐证据；隐藏 Agent 失败；将 Mock 当真实数据；忽略红队 P0 问题。

### 4.2 用户研究 Agent

职责：从真实评论、社区讨论、问答或访谈中识别用户标签、家庭环境、事件链、痛点、现有替代方案和未满足需求。

必须读取：原始用户材料及其 Evidence Cards，不得只读取二手总结。

必须输出：

```json
{
  "persona_segments": [],
  "pain_points": [],
  "event_chains": [],
  "behavior_patterns": [],
  "unmet_needs": [],
  "research_gaps": []
}
```

每个 Pain Point 必须包含用户表达、触发事件、上下文、严重度、频率口径、当前解决方法、现有方案不足和 Evidence IDs。

禁止：虚构年龄、收入或家庭结构；把功能建议当需求；用单个极端案例代表高频痛点；输出没有原始引用的“用户说”。

### 4.3 竞品 Agent

职责：标准化产品能力，区分官方声明和用户体验，建立 L1 至 L5 事件理解矩阵，定位可验证的竞品缺口。

事件理解层级：

| 等级 | 能力 |
|---|---|
| L1 | 检测单一事件 |
| L2 | 判断事件状态或持续时间 |
| L3 | 融合多个上下文 |
| L4 | 推断风险、意图或事件含义 |
| L5 | 给出行动建议或受控执行 |

必须输出：

```json
{
  "competitor_profiles": [],
  "capability_matrix": [],
  "event_understanding_levels": [],
  "competitor_gaps": [],
  "differentiation_opportunities": []
}
```

结论状态必须区分 `supported`、`partially_supported`、`unverified` 和 `not_supported`。“未找到”只能进入 `unverified`，不能自动成为“竞品没有”。

### 4.4 产品技术 Agent

职责：把用户痛点和竞品缺口转化为至少三个 Innovation，并定义事件理解链、用户流程、数据需求、系统模块、技术可行性、隐私要求和 Demo 计划。

必须依赖：已经通过证据完整性检查的用户研究与竞品 Artifact。

必须输出：

```json
{
  "innovations": [],
  "technical_assessments": [],
  "data_availability": [],
  "dependencies": [],
  "open_risks": []
}
```

必须明确视觉/传感器模型、确定性规则、时序判断、LLM 解释和人工确认各自负责什么。安全关键决定不得只由 LLM 完成。

### 4.5 商业 Agent

职责：评估用户价值、使用频率、商业路径、成本收益、生态价值和 eufy 战略匹配度。

必须依赖：用户证据、竞品分析、Innovation、技术成本和数据依赖。

必须输出：

```json
{
  "business_assessments": [
    {
      "innovation_id": "inv_xxx",
      "target_segment": "",
      "value_proposition": "",
      "usage_frequency": {},
      "revenue_paths": [],
      "cost_factors": [],
      "strategic_fit": {},
      "score_breakdown": {},
      "evidence_ids": [],
      "recommendation": "investigate"
    }
  ]
}
```

禁止：用市场规模替代需求；编造收入或转化率；默认用户愿意付费；只讲收益不讲成本。

### 4.6 红队 Agent

职责：独立攻击证据、事件理解真实性、竞品判断、技术、商业、隐私、安全与 Demo 外推风险，并强制影响结果。

必须读取：原始 Evidence、所有中间 Artifact、评分依据和调研总管摘要，不得只读取最终提案。

必须输出：

```json
{
  "red_team_reviews": [
    {
      "innovation_id": "inv_xxx",
      "critical_assumptions": [],
      "evidence_issues": [],
      "event_understanding_challenges": [],
      "competitor_challenges": [],
      "technical_risks": [],
      "business_risks": [],
      "privacy_and_safety_risks": [],
      "severity": "high",
      "required_actions": [],
      "score_adjustments": {},
      "decision": "revise"
    }
  ]
}
```

`decision` 只能是 `pass`、`revise`、`research_more` 或 `reject`。红队提出 high 严重度问题后，工作流必须返工或淘汰，不能由调研总管静默忽略。

## 5. 依赖与并行关系

```text
调研总管生成计划
        ↓
┌──────────────────┐
│ 用户研究 Agent    │
│ 竞品 Agent        │
└──────────────────┘
        ↓
证据完整性检查
        ↓
产品技术 Agent
        ↓
商业 Agent
        ↓
红队 Agent
        ↓
调研总管综合
        ↓
飞书人工场景晋级
```

用户研究和竞品研究可以并行；产品技术、商业、红队和最终综合必须按依赖顺序执行。补研只重跑受影响任务，不重复已经通过质量检查的无关任务。

## 6. 强制返工条件

以下任一条件成立时不得进入下一阶段：

- 用户痛点没有有效 Evidence；
- 竞品差异仍为 `unverified` 却被描述为不存在；
- Innovation 缺少 Event、State、两个 Context、Inference、Risk/Value 或 Action；
- 任一关键上下文没有真实数据来源或失败回退；
- 商业评分没有依据或引用；
- 红队存在未处理的 high 严重度问题；
- 最终评分与结构化分项不一致；
- Agent 输出 Schema 校验失败；
- Mock、Invalid 或跨项目 Evidence 被用于支持关键 Claim。

## 7. Agent 质量评分

| 维度 | 权重 |
|---|---:|
| 任务完成度 | 20% |
| 证据覆盖度 | 20% |
| 输出结构完整性 | 15% |
| 推理逻辑 | 15% |
| 与其他 Agent 的一致性 | 10% |
| 事件理解相关性 | 10% |
| 可执行性 | 10% |

- 低于 60：`failed`；
- 60–74：`partial`；
- 75–89：`completed`；
- 90 以上：高质量 `completed`。

质量分只决定任务状态和是否需要复核，不能代替 Evidence Gate、红队门禁或人工决策。
