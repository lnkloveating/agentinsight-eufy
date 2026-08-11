# AI Native Ecosystem Gate：后端与前端接入说明

## 1. 这一步解决什么问题

生态机会 Agent 负责提出有 Evidence 边界的候选，AI Native Ecosystem Gate 负责阻止以下伪创新继续晋级：

- 只把单次检测结果改写成通知文案；
- 只包含一个设备或一条固定 If-Then 规则；
- 移除 AI 后核心价值仍然完整成立；
- 模型同时承担权限、动作执行等确定性安全职责；
- 没有失败修订、隐私边界、离线降级或部署前验证；
- 没有人类授权点却试图执行高影响动作。

Gate 不生成新候选、不重新调用模型，也不判断技术、商业或上架结论。它只消费最新
`EcosystemOpportunityArtifact`，执行确定性检查，再把必须由人判断的语义问题投影为 Human Gate。

## 2. 当前主路径

```text
Brief Gate
→ Research Manager
→ User Research + Competitor Ecosystem Research
→ Evidence Readiness
→ Ecosystem Opportunity Agent
→ AI Native 确定性检查
→ AI Native Human Gate
   ├─ approve       → technical_feasibility_pending
   ├─ revise        → 只重跑 Ecosystem Opportunity
   ├─ research_more → 统一 Source Recovery → 只重跑 Ecosystem Opportunity
   ├─ reject        → rejected
   └─ terminate     → terminated
```

技术可行性 Agent 仍未实现，因此 `approve` 后明确返回
`awaiting_technical_feasibility`；旧 Product Technical v1 已删除，也不会错误进入商业链路。

## 3. 确定性检查

每个候选分别检查：

1. `scope_level` 必须是 `ecosystem_service`；
2. 至少两个必需设备角色真实进入跨设备信息流；
3. AI removal test 必须表明移除 AI 后核心价值不能成立，并列出丢失能力；
4. 模型职责与确定性职责必须非空且不能完全重叠；
5. 必须存在失败后的学习或修订闭环；
6. 必须声明隐私、离线、流级 fallback；
7. 必须存在权限、安全约束和 Human Review Point；
8. 部署前验证必须同时覆盖 failure 与 adversarial 场景，并声明成功和失败条件；
9. 上一层 Evidence/Capability Gate 已阻止的候选不能绕过本 Gate。

失败候选生成稳定 `revision_request_id`、受影响 Opportunity/Task、原因和修订动作。Gate 不改写原
Artifact，也不把语义推断伪装成确定性结论。

## 4. 人工必须判断什么

通过确定性检查只代表“具备 AI 原生候选结构”，仍需用户回答：

- 目标是否真的开放，还是能够预先穷举为固定规则；
- 是否跨时间维护家庭安全状态，而不是一次事件一次通知；
- 不确定时是否会主动补证、降级或询问用户；
- 验证失败后是否真的修订策略并保留授权与审计。

只有 `eligible_opportunity_ids` 中的候选可以被批准。审批时必须至少选择一个，后端拒绝选择被阻止
候选、重复 ID 或没有选择的批准请求。

## 5. Source Recovery 与 Checkpoint

如果生态机会 Artifact 带有 `portfolio_gaps`，Human Gate 才允许 `research_more`。工作流投影：

- `source_artifact_id`；
- 稳定 `gap_ids`；
- 用户真正需要补充的问题；
- `ecosystem_opportunity` 受影响任务。

前端调用现有统一 Agent Artifact Source Recovery API 创建补研任务。补研达到 `resolved` 或允许带缺口
继续后，把完整 `SourceRecovery` 交给 `WorkflowRunner.resume_source_recovery()`；Checkpoint 只恢复并重跑
生态机会节点，不重复运行已经完成的用户研究和竞品研究。

## 6. 前端展示

AI Native Gate 页面应显示：

- 候选的八项确定性检查及失败原因；
- `human_review_required` 与 `blocked`，不能用一个笼统的 Failed 代替；
- 四个语义审查问题；
- 可选择的 Opportunity ID；
- “批准进入技术验证”“要求修订”“补充资料”“淘汰”“终止”五类动作；
- `awaiting_source_recovery` 时显示统一补研弹窗；
- `awaiting_technical_feasibility` 时明确说明下一 Agent 尚未运行，不能显示“可落地”或“可上架”。

当前没有新增公共 HTTP API；Human Gate 和恢复语义通过现有 LangGraph/Runner 契约承载，后续工作流 API
分支再把 Checkpoint 操作投影给前端和飞书。
