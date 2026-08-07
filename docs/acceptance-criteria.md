# MVP Acceptance Criteria

每条标准必须映射到自动化测试、可重复演示步骤或两者。验收对象是从飞书 Aily 发起、经过真实证据和候选比较、在飞书完成人工决策、运行晋级场景 Demo 并生成可追溯结论的完整链路。

## AC-01 飞书 Aily 研究入口

给定一个模糊的智能家居研究问题，Aily 能追问市场、用户、品类、品牌、时间、数据来源和 Innovation 约束，生成符合 `ResearchBrief` 契约的结构化结果；用户确认后，Aily 通过 `create_research` API Skill 创建后端项目并返回 `project_id` 与 Web 地址。

Aily 必须实际完成意图澄清和技能调用，不能只发送静态链接或预设文本。

## AC-02 项目生命周期

项目遵循 `docs/state-machine.md`。无效转换被拒绝；每个有效转换保存时间、actor、reason、trace_id 和 checkpoint_id。`completed`、`rejected` 与 `terminated` 含义不同且不可互换。

## AC-03 六 Agent 职责与依赖

调研总管生成计划；用户研究与竞品研究并行；产品技术等待二者通过证据门；商业评估等待产品技术；红队读取原始 Evidence 和所有中间 Artifact；调研总管最后综合。

每类 Agent 使用独立输入、输出 Schema、质量标准和失败条件。Schema 校验失败或依赖不完整时不得伪装成完成。

## AC-04 真实 Evidence Lake

每条 Evidence 保存稳定 ID、来源 URL、域名、来源类型、原始引用、Claim 类型、产品、地区、用户标签、发布时间、采集时间、状态、内容 Hash 和置信度。

缓存、URL 规范化、内容去重、来源多样性和预算限制可验证。采集失败单独保存为 Collection Job 结果，并计入覆盖率缺口。

用户或企业提供的文件、视频、数据集和公开链接必须先登记为项目隔离的 `SourceAsset`，保存授权依据、内容 Hash、媒体类型和 Collection Job。上传内容不得直接成为 Evidence；只有带原始位置引用的解析结果通过确定性校验后才能进入 Evidence Lake。重复资料应复用既有资产，删除文件后保留最小审计记录且不得再向 Runtime 提供内容。

## AC-05 Claim Gate

事实性 Claim 没有至少一个同项目、非 Mock、非 Invalid 且可回溯的 Evidence ID 时，不能晋级或进入最终报告。竞品“未验证”不能被改写为“没有”。冲突、未知项和被排除 Claim 保持可见。

## AC-06 Event Understanding Gate

每个候选 Innovation 必须包含：

```text
Base Event
+ Event State
+ 至少两个 Context Signals
+ Inference
+ Risk or Value
+ Recommended Action
```

每个 Context Signal 都要记录来源、可获得性、授权、时效、延迟、置信度和失败回退。缺少任一结构的候选不能进入技术评审或场景晋级门。

## AC-07 候选场景比较

在证据允许时，系统至少生成三个候选事件理解场景，并用统一权重比较用户痛点、频率、证据、竞品差异、事件理解完整度、技术与数据可行性、商业价值和 Demo 可行性。

每个分项保存理由和 Evidence IDs；如果真实证据不足以支持三个候选，系统必须显示缺口，不能用 Mock 补足数量。

## AC-08 红队真实影响结果

每个重点候选接受一次独立红队检查。红队能读取原始 Evidence，能够降分、要求补研、要求修改或淘汰候选。未处理的 high 严重度问题阻止候选进入人工晋级。

验收演示中至少一个候选必须因为红队结论发生分数、状态或推荐结果变化。

## AC-09 飞书 Human in the Loop

Brief、候选场景和最终建议三个 Gate 能保存 Checkpoint 并暂停。飞书展示结构化依据，通过 Aily 或消息卡片提交 `approve/revise/research_more/reject/terminate`，后端校验 decision_id、操作者、允许操作和幂等键后恢复。

重复、过期或与当前 Gate 不匹配的决定必须返回冲突错误，不能重复运行工作流。

## AC-10 Package Risk Intelligence Demo

当 Package Risk Intelligence 通过场景晋级时，Demo 至少消费：

- `package_delivered`；
- `package_still_present`；
- `resident_not_home`；
- 天气或另一个可验证外部风险信号。

Demo 输出结构化 Inference、Risk、Action、输入来源、模拟标记、指标、限制和 Evidence IDs。关键上下文缺失时必须降级为 `partial` 或 `inconclusive`，不能生成高置信度风险。

## AC-11 Checkpoint 恢复

强制一个 Evidence 来源或 Demo 外部数据源失败后，系统从最近有效 Checkpoint 恢复，只重跑受影响任务，不重复已经通过质量检查的节点。原始失败、重试次数和降级结果继续保留。

## AC-12 Deep Research Web

五类核心体验可操作：创建/查看 Brief、研究现场、Evidence 中心、候选场景竞技场、最终提案与方法对照。页面显示 loading、empty、failed、blocked、resumed、rejected 和 completed 状态。

Web 负责复杂证据下钻和 Trace；飞书负责轻量入口、通知、审批和结果沉淀，两者读取同一后端状态。

## AC-13 可观测性

Project、Workflow Run、Agent Run、A2A Task、MCP Call、Collection Job、Evidence、Claim、Innovation、Decision、Demo Result 和 Feishu Delivery 共享可关联标识。外部 AgentInsight 不可用时，本地 Trace 仍能支持完整审计。

## AC-14 最终结论

最终报告只能是 `recommend`、`investigate` 或 `do_not_recommend`，并包含：

- 目标用户和事件链；
- 原始证据与覆盖率；
- 竞品事件理解矩阵；
- 候选比较和淘汰理由；
- 晋级 Demo 结果与限制；
- 技术、数据、隐私和商业评估；
- 红队问题及处理结果；
- 人工决定；
- 未知问题、补研条件和停止条件。

报告关键事实可反向定位到 Claim 和 Evidence；Demo 可运行不能被描述为产品已经具备正式上架条件。

## AC-15 方法对照

AI 辅助组和传统组可以比较完成时间、有效 Evidence、引用覆盖、来源多样性、伪需求识别、重复产品发现、技术风险发现、决策可追溯性、盲评得分、成本与延迟。

如果 AI 组只提升速度而没有提升证据质量或产品判断，系统不能宣称方法更优。

## Release gate

MVP 只有同时满足以下条件才可通过：

1. 用户从 Aily 创建一个北美家庭安防研究项目；
2. Brief 在飞书确认后启动真实后端工作流；
3. 用户研究与竞品研究使用真实、可追溯 Evidence；
4. 系统比较至少三个候选，或明确显示真实证据不足；
5. 红队让至少一个候选降分、返工或淘汰；
6. 用户在飞书批准一个候选进入 Demo；
7. Package Risk Intelligence 完成一次多上下文风险判断和一次缺失上下文降级；
8. 系统承受一次强制外部失败并从 Checkpoint 恢复；
9. 最终结论可选择 `do_not_recommend`，不强行立项；
10. 最终报告关键事实、候选淘汰和人工决定全部可追溯。

验收不以 Agent 数量、抓取网页数量、生成文本长度或 Demo 视觉效果代替上述链路。
