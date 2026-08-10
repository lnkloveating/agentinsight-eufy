# 竞品生态分析后端与前端接入说明

## 1. 这一分支解决什么问题

旧竞品综合回答的是“某一款设备有哪些优点、缺点和价格/评价事实”。这仍然有用，但不能回答 AI 原生家庭安防真正关心的问题：多个设备是否协作、是否持续维护家庭状态、证据不足时如何补证、断网如何降级、隐私与照护授权如何处理。

当前链路把两层明确分开：

```text
已确认的竞品候选与产品资料
→ 官方产品 / 价格渠道 / 用户评价三个 A2A 事实专家并行
→ 产品事实综合（内部上游，保留准确产品血缘）
→ 竞品生态综合（目标/对照生态 × 12 个能力维度）
→ 确定性 Evidence、范围和覆盖审计
→ CompetitorEcosystemArtifact v2
→ ResearchHandoff
```

没有另起一个会自行改变研究范围的“生态发现模型”。目标生态和对照生态由用户确认的 Research Brief 决定；具体产品候选继续复用已有 Competitor Discovery、Candidate Gate、Source Onboarding 和 Evidence 链路。

## 2. 真实接口

```http
POST /api/v1/projects/{project_id}/agents/competitor-ecosystem
GET  /api/v1/projects/{project_id}/agents/competitor-ecosystem/artifacts
```

运行前项目必须已经通过 Brief 确认，并处于 `researching` 或 `supplementing_research`。POST 会使用项目模型选择策略，依次完成三类事实专家、产品事实综合和生态综合；每次运行由 Runtime 保存 Agent Run、模型调用审计和版本化 Artifact。

## 3. 12 个生态比较维度

- `safety_goal_coverage`：覆盖哪些家庭安全目标；
- `cross_device_orchestration`：多个设备是否能协作；
- `temporal_state_understanding`：是否能跨时间维护事件/家庭状态；
- `active_perception`：信息不足时是否主动请求补充信号；
- `uncertainty_handling`：不确定时是否降级、询问或继续观察；
- `intervention_ladder`：是否支持由提醒到高影响动作的分级干预；
- `local_cloud_partition`：设备、HomeBase、本地与云如何分工；
- `privacy_and_consent`：被保护者、照护者和家庭成员如何授权；
- `offline_fallback`：断网、离线或模型不可用时如何降级；
- `caregiver_workflow`：照护者如何接收、确认和升级事件；
- `failure_recovery`：误判或用户纠正后策略如何修订；
- `business_model`：硬件、订阅和服务模式的已知边界。

## 4. 前端应该怎样展示

竞品页建议分成四层：

1. 顶部显示目标生态、对照生态、本次 Artifact 版本、状态与 Evidence 审计结果；
2. 中间显示“生态 × 12 维度”矩阵，状态使用 `supported / limited / contradicted / unknown`；
3. 点击非 unknown 单元格，展示 statement、explanation、具体产品、来源专家和 Evidence IDs；
4. 点击 unknown 单元格，展示 `unknown_reason` 或 `research_gaps`，提供统一补研入口。

`unknown` 的中文应写“当前资料未覆盖”或“需要补研”，不能写“竞品不支持”。`opportunity_signals` 只能显示成“待下游验证的缺口假设”，不能显示成已确认的未来产品机会。

页面还应提供“查看具体产品事实”抽屉，用于查看生态判断来自哪款设备、哪个价格渠道或哪些用户评价。这样生态结论仍可追溯，而不是把旧单品分析删除后丢失证据。

## 5. 状态与失败语义

- `completed`：Brief 要求的所有生态与 12 个维度均有合格 Evidence，三个事实专家完整，且无高严重度缺口；
- `partial`：已有可用生态判断，但仍有 unknown、未映射产品、缺失生态或高严重度补研问题；
- `blocked`：三个事实专家无法形成足够上游，生态模型不应被调用或不能形成受审计结果；
- Runtime/模型不可用：接口返回安全分类的 4xx/5xx 错误，不保存伪 Artifact。

## 6. 明确不包含

本分支不生成未来生态方案，不判断技术可行性、商业收益或是否上架，也不控制真实家庭设备。下一分支 `agent/ecosystem-opportunity` 才会消费用户研究、竞品生态 Artifact、共享 Evidence 和 Device Capability Graph，生成待验证的生态机会候选。
