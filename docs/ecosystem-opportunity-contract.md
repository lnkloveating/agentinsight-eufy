# 生态机会契约（Ecosystem Opportunity Contract）

> 历史说明：本文记录 `domain/ecosystem-opportunity-contract` 当时仅定义公共契约的边界。
> 真实 Agent、Model Adapter、Device Capability Graph 投影和 `/api/v1` Route 现已由
> `agent/ecosystem-opportunity` 完成；当前接入方式以 `docs/ecosystem-opportunity-agent.md` 为准。

> 分支：`domain/ecosystem-opportunity-contract`
>
> 基线：`main`（合并交接文档后的最新提交）
>
> 状态：只定义公共契约与领域模型，不含 Prompt、模型调用、Agent Service、FastAPI Route、
> 设备能力图、AI Native Gate 或商业评估。

## 1. 契约目标

为 eufy 家庭安防生态方向建立第一层公共词汇，让系统能够在**类型层**明确区分：

- `device_feature`：单设备功能；
- `device_product`：独立设备产品；
- `ecosystem_service`：跨设备生态服务。

并让一个"生态级解决方案机会"能够结构化表达：用户安全目标、目标用户与问题、需要哪些设备角色与能力、
跨设备信息如何流动、部署在设备/HomeBase/云/混合、隐私与权限边界、离线与失败时如何降级、为什么必须
使用 AI、去掉 AI 后核心价值是否成立、如何验证、引用了哪些 Evidence、还缺什么资料、是否通过后端 Gate。

本分支只负责**定义契约并做确定性结构校验**。语义层判断（是否真的 AI 原生、是否真正形成跨设备闭环、
是否只是普通自动化包装、隐私与降级是否充分、是否值得晋级）留给后续分支 `workflow/ai-native-ecosystem-gate`。

## 2. 关键设计：模型可输出字段 vs 后端拥有字段

契约把"模型允许输出的字段"和"后端拥有的字段"分离：

| 层 | 类型 | 说明 |
|---|---|---|
| 模型输出 | `EcosystemOpportunityModelCandidate` / `EcosystemOpportunityModelGap` / `EcosystemOpportunityModelOutput` | 只含模型可负责的字段；**不允许**出现 `gate_status`、`gate_issues` 或任何确定性判定，由 `extra="forbid"` 在结构层强制 |
| 后端拥有 | `EcosystemOpportunityCandidate` / `EcosystemOpportunityGap` | 在模型字段上追加 `gate_status`、`gate_issues` 和确定性 `gap_id` |

`gap_id` 由 `ecosystem_opportunity_gap_id(question, opportunity_ids)` 确定性生成（与顺序无关），
模型不能自行生成不稳定 ID。

契约还提供以下确定性一致性保证：

- 设备角色和 AI 移除测试中的 Evidence ID 必须同时出现在候选顶层 Evidence 允许集合中，统一审计不会
  遗漏嵌套引用；
- `schema_name`、`schema_version`、`artifact_type` 和可发布状态与 OpenAPI 常量保持一致；
- Artifact 级 Evidence ID、Gate Issue 和其他标识列表保持唯一；
- Coverage 数量必须与实际候选、通过 Gate 的候选及生态服务候选相等；
- `portfolio_gaps` 只能定向到当前组合中真实存在的 Opportunity；
- 少于目标三个候选时必须保留至少一个组合缺口，不能只降低数量而不解释原因。

主要类型：`SolutionScope`、`EcosystemDeploymentTarget`、`EcosystemScenarioType`、`DeviceRoleType`、
`RequiredDeviceRole`、`CrossDeviceInformationFlow`、`EcosystemBlueprint`、`AIRemovalTest`、`AINativeCase`、
`EcosystemValidationPlan`、`EcosystemOpportunityModelCandidate` / `EcosystemOpportunityCandidate`、
`EcosystemOpportunityModelGap` / `EcosystemOpportunityGap`、`EcosystemOpportunityModelOutput`、
`EcosystemOpportunityCoverage`、`EcosystemOpportunityPayload`、`EcosystemOpportunityArtifact`。

代码位置：`src/backend/app/agents/ecosystem_opportunity/contracts.py`。

## 3. 当前 Artifact 边界

`EcosystemOpportunityArtifact` 是新项目唯一的机会生成契约。它以生态级解决方案
`EcosystemOpportunityCandidate` 为语义单元，通过 `SolutionScope` 区分 device_feature、
device_product 与 ecosystem_service，并用 `EcosystemBlueprint`、`AINativeCase` 和
`EcosystemValidationPlan` 表达跨设备协作、AI 必要性和验证计划。

旧单产品 Product Technical v1 契约、API、模型 Adapter 和专属恢复入口已删除。通用
`ResearchArtifact`、Evidence 和 Source Recovery 能力继续保留。

## 4. 前端未来如何读取

`docs/api/openapi.yaml` 与 FastAPI 已实现以下接口：

- `POST /projects/{project_id}/agents/ecosystem-opportunity`
- `GET  /projects/{project_id}/agents/ecosystem-opportunity/artifacts`

响应为 `EcosystemOpportunityArtifact`。生态机会卡片可展示：`scope_level`、用户安全目标、依赖设备角色、
跨设备信息流、AI 必要性（`AINativeCase` / AI 移除测试）、竞品差异（`competitor_gap_ids`）、技术假设、
已知盲区、Evidence coverage、`gate_status` 与补研按钮（`portfolio_gaps` + 稳定 `gap_id`）。

在真实 Agent 与 Route 上线前，前端只能把这些结构当作占位契约设计，不得表示为已生成的真实生态方案。

## 5. 当前明确不包含

真实大模型调用、Ecosystem Opportunity Prompt、Agent Adapter、Agent Service、FastAPI 真实 Route、
Device Capability Graph、AI Native Gate、Technical Feasibility Agent、Security Policy Compiler、
商业 Agent、红队 Agent、包裹 Demo、真实 eufy 设备 API、固定 Guardian Agent 输出、Mock 研究结论。

`ECOSYSTEM_OPPORTUNITY` 已加入 `ResearchAgentType` 和 `RecoverableAgentType` 枚举，但**暂不接入主图**
（主路径仍以 `app/workflows/planning.py` 的 `PLANNED_AGENT_TYPES` 为准）。本分支未新增补研 Service 或 API，
也未新增数据库表或迁移（纯契约）。

## 6. 下一分支

`evidence/device-capability-graph`：建立带 Evidence 血缘的设备能力图和用户家庭设备快照，
用于回答"这个家庭现有设备能否支撑某个生态策略"，为后续技术可行性与安全策略编译提供确定性事实来源。
