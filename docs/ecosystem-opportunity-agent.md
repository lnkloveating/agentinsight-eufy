# 生态机会 Agent：后端与前端接入说明

## 1. 这一步解决什么问题

生态机会 Agent 不再输出一款固定门铃或固定老人照护产品。它把四类真实输入交叉验证：

```text
AI Native Research Brief
＋ 最新 UserResearchArtifact
＋ 最新 CompetitorEcosystemArtifact
＋ 共享 Evidence / Device Capability Graph
→ 动态生成 0～5 个生态机会
→ 后端 Evidence 与设备能力门禁
→ 版本化 EcosystemOpportunityArtifact
```

目标是 3 个候选、硬上限 5 个。证据只能支持更少候选时，系统返回更少候选和明确的
`portfolio_gaps`，不会复制老人、包裹、门铃或 Guardian 模板凑数。

## 2. 真实接口

```http
POST /api/v1/projects/{project_id}/agents/ecosystem-opportunity
GET  /api/v1/projects/{project_id}/agents/ecosystem-opportunity/artifacts
```

项目必须已经通过 Brief 确认，状态为 `researching` 或 `supplementing_research`。POST 使用项目的
模型选择策略调用真实 Model Gateway，并由 Runtime 保存 Agent Run、模型调用、输入 Artifact 血缘和
输出 Artifact 版本。GET 按版本顺序返回历史结果。

## 3. 设备能力如何处理

Context Builder 每次运行都会读取当前项目的 Device Capability Graph，并重新检查 Evidence 状态：

- 只有设备身份与能力断言都引用 `verified` 或 `partially_verified` Evidence，能力才进入模型上下文；
- `supported + available` 且没有相反证据时，候选可以把它写成现有能力；
- 没找到、状态未知、明确不支持、不可用或证据冲突时，只能写进 `technical_hypotheses`；
- 未确认能力会确定性生成 `portfolio_gap`；明确不可用或证据冲突还会阻止候选晋级；
- 设备角色引用的 Evidence 必须来自本次能力图投影，不能借普通网页 Evidence 冒充设备能力。

因此，“方案需要某能力”和“eufy 当前设备已经具备某能力”是两个不同结论。

## 4. 后端门禁

模型只负责提出候选，以下判断由后端完成：

- 所有引用必须属于本次 Research Handoff、补研 Evidence 或能力图；
- 每个候选至少同时引用用户研究和竞品生态 Evidence；
- `competitor_gap_ids` 必须是竞品生态 Artifact 中真实存在的机会信号；
- 候选名称和安全目标不得重复；
- `ecosystem_service` 至少需要两个设备角色和一条跨设备信息流；
- 已证实能力必须引用能力图 Evidence；未知能力必须显式标为技术假设；
- Coverage、状态、稳定 Gap ID、质量分和 Artifact Evidence 集合由后端计算。

这一分支只做证据/能力边界门禁。更严格的 AI removal test、主动感知闭环和“普通自动化伪装成 AI
原生”的判断已经由 `workflow/ai-native-ecosystem-gate` 完成，见
`docs/ai-native-ecosystem-gate.md`。

## 5. 前端展示建议

“生态机会”页可以按以下顺序展示：

1. 顶部显示 Artifact 状态、版本、候选数、可晋级数、Evidence 覆盖和运行时间；
2. 每张候选卡显示 `scope_level`、安全目标、目标用户、问题和 `gate_status`；
3. “设备与信息流”展开区显示所需设备角色、所需能力、跨设备数据流、部署位置、隐私/权限边界、
   离线与失败降级；
4. “为什么必须用 AI”显示模型职责、确定性职责和 AI removal test，但在下一 Gate 完成前标记为
   “待 AI 原生门禁验证”；
5. “证据”抽屉按用户、竞品和设备能力三类展示 Evidence ID，并允许下钻原始 Evidence；
6. `gate_status=blocked` 时展示 `gate_issues`；`portfolio_gaps` 通过现有统一补研弹窗收集文字、文件
   或企业 Evidence；
7. `completed`、`partial` 和 `blocked` 分别显示“证据充分”“已有候选但仍需补研”和“没有可晋级
   候选”，不能把 `partial` 写成研究失败。

前端不应把 `technical_hypotheses` 显示为“现有设备能力”，也不应在用户审批和后续 Gate 之前显示
“可上架”。

## 6. 当前不包含

- 已由后续分支接入 LangGraph 主图并执行 AI Native Ecosystem Gate；
- 尚未完成技术可行性、策略编译、策略仿真、商业结论和红队修订；
- 尚未控制真实家庭设备，也没有用假 eufy API 冒充企业联调；
- Package Demo 仍是后续对最终晋级策略的一个可落地验证样例，不是固定研究结论。
