# AgentInsight × eufy 后端开发交接

> 更新时间：2026-08-10
>
> 用途：换 Codex 账号、换开发者或发生上下文压缩时，以这份文件恢复项目状态。
>
> 开发范围：当前团队只负责后端，但必须让前端组知道最终产品、输入、状态、弹窗和结果应该是什么样。

## 0. 新账号先做什么

新账号打开仓库后，先执行以下要求，不要立即改代码：

```text
完整阅读：
1. AGENTS.md
2. docs/CODEX_HANDOFF.md
3. docs/acceptance-criteria.md
4. docs/api/openapi.yaml
5. docs/ai-native-eufy-ecosystem-handoff.md
6. docs/backend-progress-summary.md
7. docs/device-capability-graph.md
8. docs/ai-native-home-safety-research-scope.md

然后检查：
- git status -sb
- git log --oneline --decorate -15
- git branch -a
- git stash list

先向用户总结项目目标、当前状态、工作区未提交内容、下一分支和验收标准，再继续开发。
```

仓库约束：

- 公共 API 必须先更新 `docs/api/openapi.yaml`；
- 最终报告中的事实没有 Evidence ID 就不能发布；
- 确定性解析、校验、权限和持久化必须与 LLM Prompt 分开；
- 不提交 Key、个人数据、家庭视频、运行 Trace、抓取快照和生成 Evidence；
- 不使用 Mock 冒充真实模型、企业 API 或真实调研结果；
- 每一步使用中文 Commit，并在最低有用层级补测试；
- 分支名不加 `codex/` 前缀，这是用户明确偏好。

## 1. 项目最终目标

本项目不是“让 AI 固定设计一款新门铃”，而是一个证据驱动的 eufy AI 原生家庭安防生态定义与验证系统。

最终业务链路：

```text
用户提出模糊研究目标
→ AI 追问并生成 Research Brief
→ 用户确认范围、地区、目标家庭和资料授权
→ 用户研究 + 竞品生态研究并行
→ 共享 Evidence Lake 与资料准备度检查
→ 动态生成多个生态级安全机会
→ 设备能力图证明需要哪些设备角色、真实能力和缺口
→ AI Native Gate 淘汰“普通自动化换皮”
→ 技术可行性 Agent 判断现有技术、数据、隐私和部署是否支持
→ Security Policy Compiler 把安全目标编译成跨设备策略
→ 动态场景验证主动寻找失败
→ 商业 Agent 判断是否值得试点，不伪造收益
→ 红队和用户质疑触发定向返工
→ 选中的生态机会进入包裹 Goal-to-Guard Demo
→ 输出可试点 / 有条件试点 / 不建议试点
→ 飞书 Aily 完成入口、通知、审批和文档沉淀
```

核心创新不是“我们也有多 Agent”，因为企业内部可能已有更强的协作系统。创新重点是：

> 把模糊家庭安全目标，自动转换为可解释、可验证、可降级、可被红队推翻的跨设备安全策略。

简称 **Goal-to-Guard**：从用户安全目标，到可执行并经过验证的守护策略。

## 2. 什么叫 AI 原生生态

系统提出的候选必须能够表达：

- 用户想保护什么，而不是先假定购买某个硬件；
- 门铃、摄像头、门磁、HomeBase、App 和外部上下文各自承担什么角色；
- 设备之间传递什么信息；
- AI 在事件理解、上下文融合、不确定性处理和策略调整中做什么；
- 去掉 AI 后核心价值是否仍成立；
- 证据不足、设备离线、视野遮挡或授权不足时如何降级；
- 用什么场景和失败条件验证；
- 需要哪些 Evidence，哪些仍是假设。

只增加一个检测标签、一个硬件规格或一条固定 If-Then 自动化，不应伪装成生态级 AI 原生机会。

包裹保护是第一个验证 Demo，不是研究 Agent 必须输出的固定答案。研究证据支持其他机会时，系统必须输出其他候选；
如果证据无法支持包裹方向，也必须允许“不建议立项”。

## 3. 当前开发状态

### 3.1 已合并到 `main` 的新方向基础

设备能力图合并提交为：

```text
6cc8cec 合并设备能力图
```

已完成：

- `domain/ecosystem-opportunity-contract`；
- 生态候选区分 `device_feature / device_product / ecosystem_service`；
- `EcosystemBlueprint`、设备角色、跨设备信息流、部署位置、隐私边界、离线降级；
- `AINativeCase` 与 AI Removal Test；
- Evidence 引用、Coverage、Gap、Artifact 类型和版本的确定性校验；
- 历史 Product Technical v1 Artifact 结构仍可读取，但不再定义新项目 Research Brief。

该分支只定义“生态方案长什么样”，还没有真实生态机会 Agent。

### 3.1.1 AI 原生家庭安防研究范围

`domain/ai-native-home-safety-research-scope` 已完成以下迁移：

- 新项目只接受 `home_safety_ecosystem` Research Brief；
- 删除旧 `category / target_user / region / scenarios / constraints / focus_dimensions` 输入；
- 增加安全领域、目标/对照生态、安全目标、授权信号、隐私边界、干预边界、禁止推断、验证要求与资料权限；
- 用户研究、竞品主管、资料发现、片段 Evidence 和资料要求服务统一消费新字段；
- 所有创建项目和直接构造 Brief 的测试已改为生态研究输入；
- 旧字段会被确定性拒绝，不做静默兼容；
- 历史迁移和旧 Artifact 只用于已有数据兼容，不能作为前端当前入口展示。

详细边界见 `docs/ai-native-home-safety-research-scope.md`。

### 3.2 已完成分支：`evidence/device-capability-graph`

该分支已完成、合并到 `main`，提交为：

```text
00f942e 定义设备能力图公共接口与验收标准
356ce5f 实现证据约束的设备能力图
50336d6 补充设备能力图接口与迁移测试
0f57e74 完善设备能力图文档和开发交接
6cc8cec 合并设备能力图
```

已完成内容：

- `app/schemas/device_capability.py`；
- `app/infrastructure/database/models.py` 中五类能力图表；
- `app/infrastructure/database/device_capability_repository.py`；
- `app/application/device_capabilities/service.py`；
- `app/api/v1/routes/device_capabilities.py` 与依赖/路由注册；
- `migrations/versions/0019_device_capability_graph.py`；
- Alembic 外部连接注入，供内存迁移测试使用；
- 契约、查询、HTTP、迁移四组测试；
- `docs/device-capability-graph.md`；
- 本交接文件与进度文档更新。

新增真实 `/api/v1`：

```text
POST   /projects/{project_id}/device-capabilities/catalog
GET    /projects/{project_id}/device-capabilities/catalog
GET    /projects/{project_id}/device-capabilities/catalog/{catalog_device_id}
PUT    /projects/{project_id}/device-capabilities/catalog/{catalog_device_id}
DELETE /projects/{project_id}/device-capabilities/catalog/{catalog_device_id}
PUT    /projects/{project_id}/device-capabilities/household-snapshot
GET    /projects/{project_id}/device-capabilities/household-snapshot
POST   /projects/{project_id}/device-capabilities/queries
```

新增迁移头：

```text
0019_device_capability_graph
```

已验证：

```text
Ruff：通过
Mypy：207 个 app 源文件通过
全量 Pytest：305 passed，1 个第三方 Starlette TestClient 弃用警告
Alembic：内存数据库从空库升级到 head，再降级到 0018，通过
OpenAPI：3.1 YAML 解析通过
git diff --check：通过
```

迁移测试遗留目录 `src/backend/device-capability-migration-1onkisii` 已清理，功能分支工作区在合并前保持干净。
下一位开发者不需要重新实现设备能力图，应从 `agent/ecosystem-opportunity` 开始。

### 3.3 旧商业草稿

旧 `agent/commercial-evaluation` 分支已经删除。它围绕单产品候选设计，不应恢复或合并。

本机曾保留一份可恢复的旧草稿：

```text
stash@{0}: 归档旧商业评估未完成草稿
```

它不在 GitHub 中，也不是当前实现依赖。除非用户明确要求参考，否则不要应用；未来商业 Agent 必须使用
`agent/commercial-evaluation-v2`，消费生态机会、技术可行性和验证成本。

## 4. 已完成的后端基础能力

以下能力已经在之前分支逐步完成：

- 项目生命周期、Brief Gate、SSE、Checkpoint 和 Human Gate 底座；
- LangGraph 并行用户/竞品研究、主路径桥接和定向恢复；
- Agent Runtime Gateway、内部模型 Adapter、OpenCode CLI Runtime 和 A2A；
- 多模型 Model Gateway、GLM 5.2 / DeepSeek V4 Pro、结构化输出、重试和 Token 审计；
- 统一 Source Ingestion：文件、链接、授权、哈希去重和项目隔离；
- 安全网页解析、确定性文档解析、媒体音轨/抽帧基础；
- 当前没有真实 ASR/视觉 Connector，视频语义理解必须显示 blocked；
- Tavily 搜索发现，只输出候选 URL，不把搜索摘要当 Evidence；
- Source Routing、Source Requirements、Source Recovery 与通用资料不足弹窗契约；
- Fragment → 人工审核 → Evidence Lake；
- 共享 Evidence Retrieval，当前是可解释词法/元数据检索，不应宣传成向量 RAG；
- 用户研究 Agent；
- 竞品发现、Candidate Gate、来源接入和资料发现；
- 竞品官方产品、价格渠道、用户评价三个 A2A 专家；
- 竞品综合、证据审计和主路径桥接；
- Product Technical v1 历史实现仍供主图迁移期间内部读取，不再定义 Research Brief 或新方向最终产物；
- Ecosystem Opportunity 公共契约；
- Device Capability Graph（已完成并合并到 `main`）。

## 5. 前端最终成品应该是什么样

我们只开发后端，但接口和状态必须服务下面的前端体验。前端不应只是一个“输入一句话，等待长报告”的页面。

### 5.1 首页 / Deep Research 输入

主输入示例：

```text
分析 eufy 未来三年的 AI 原生家庭安防生态机会，重点关注北美家庭、跨设备协作、隐私和可落地验证。
```

输入区应包含：

- 研究问题；
- 目标地区、用户、时间范围和重点维度；
- 模型选择器，只读取后端 `/models`，不接触 API Key；
- “通用生态研究”和“结合我的家庭设备验证”两种模式；
- 资料中心入口：网页、PDF、文本、表格、图片、视频/字幕；
- 企业内部资料授权说明；
- 可选家庭设备清单；
- 开始前的 Research Brief 确认。

如果用户只输入“分析 eufy 未来产品机会”，Research Brief Agent 应继续追问，并只提交新的生态范围契约：

- 研究 eufy 整体生态还是具体地区/家庭类型；
- 更关注防盗、包裹、老人儿童、车库、周界还是隐私；
- 是否允许使用公开竞品资料；
- 是否有企业资料和家庭设备清单；
- 最终需要行业报告、生态方案、可运行 Demo 还是试点建议。

### 5.2 统一资料中心

资料中心不是按 Agent 分成多个重复上传入口。用户只上传一次，后端自动路由为：

- 用户研究；
- 竞品官方产品；
- 价格渠道；
- 用户评价；
- 设备能力；
- 技术论文/标准；
- 商业和企业内部数据。

每份资料展示：

```text
已授权 → 已解析 → 待确认分类 → 已确认 → 已审核片段 → Evidence 可用
```

网页被反爬、内容过少或视频无法语义解析时，不能无限重试或假装成功。前端弹窗直接问用户补充系统真正缺少的字段，
支持文本、PDF、截图或字幕；替代链接只是可选项，不强迫用户继续换网站。

### 5.3 研究运行页

运行页显示：

- Research Manager；
- User Research；
- Competitor Supervisor 与三个 A2A 专家；
- Ecosystem Opportunity；
- AI Native Gate；
- Technical Feasibility；
- Policy Compiler / Verification；
- Commercial；
- Red Team；
- Final Synthesis。

每个节点显示 waiting/running/completed/partial/blocked/failed、使用模型、Evidence 数量、耗时和错误。前端通过 SSE
展示运行历史，不轮询伪造进度条。

### 5.4 竞品分析页改为“竞品生态”

不能只比较一个门铃规格。竞品页应比较 Ring、Google Nest、Arlo 等生态在以下维度的能力：

- 门铃、摄像头、门磁、Hub、App 和订阅之间如何协作；
- 本地/云端计算与存储；
- 事件理解和跨摄像头/跨传感器上下文；
- 自动化规则、开放接口和第三方集成；
- 离线能力、隐私、授权和失败降级；
- 用户评价中的真实优缺点；
- 价格、渠道、订阅和地区边界；
- 哪些能力有 Evidence，哪些只是缺资料，不能把“未发现”写成“竞品没有”。

最终 CompetitorArtifact 进入主路径，成为生态机会的差异化约束，而不是单独生成一篇孤立报告。

### 5.5 设备能力页

前端提供两层视图：

1. “eufy 已证明的设备能力目录”；
2. “这个家庭实际安装和授权的设备”。

目录卡片显示厂商、产品、型号、品类、能力、Evidence、离线/授权/数据位置和冲突。家庭快照只让用户填写粗粒度
位置与状态，界面明确说明不需要上传实时家庭视频或填写序列号。

能力查询结果使用四种状态：

```text
available   已有设备和证据可以支撑
unavailable 已知不能支撑或当前离线/拒绝授权
unknown     资料或设备映射不足，需要补充
conflict    合格资料互相冲突，需要人工处理
```

### 5.6 生态机会卡片

Agent 动态生成目标 3 个、最多 5 个候选；资料不足可以少于 3 个，但必须解释缺口，不能用固定模板凑数。

每张卡片展示：

- 用户安全目标；
- `device_feature / device_product / ecosystem_service`；
- 需要的设备角色和能力；
- 当前 eufy 设备可匹配、缺失、未知和冲突的部分；
- 跨设备信息流；
- 设备端、HomeBase、云端的部署位置；
- AI 必要性和 AI Removal Test；
- 隐私、权限、离线和 fallback；
- 竞品差异；
- Evidence 覆盖；
- 验证计划和补研按钮；
- Gate 状态。

Agent 输出的是“需要哪些设备角色和能力”，设备能力图负责匹配具体型号。不要在 Prompt 中固定写死 E340、HomeBase 3
或包裹场景。

### 5.7 通用资料不足弹窗

任何 Agent 发现资料不足都投影为统一 Gap：

```text
当前无法确认：HomeBase 是否支持此策略需要的本地事件融合。
为什么需要：它决定断网时策略能否继续工作。
可以补充：官方说明、企业内部能力说明、PDF/截图或授权文本。
影响：机会 eco_02 的技术可行性与离线降级。
```

用户可以提交资料、填写结构化事实或选择“不知道”。选择“不知道”后流程可以继续，但状态必须是 `unknown`、
`partial` 或“有条件试点”，不能自动变成通过。

### 5.8 红队与用户质疑

红队不只是模型自己提问题。页面允许导师、企业人员或用户输入质疑，例如：

- 家人取件为什么不会误报？
- 门铃被遮挡怎么办？
- 断网后还能工作吗？
- 陌生人和快递员如何区分？
- 为什么竞品无法复制？
- 收益依据在哪里？

后端把问题变成 `RevisionRequest`，定位 Claim、Evidence、Opportunity、Policy 和 Scenario，只重跑受影响节点。回答
不了时应降低结论、补研、降级策略或淘汰候选，不允许只生成一段安慰性解释。

如果所有候选都被淘汰，系统仍然输出有价值结果：

- `do_not_recommend`；
- 被淘汰原因；
- 仍缺的证据；
- 重新研究的触发条件；
- 最小可行的降级方案；
- 不建议浪费资源做什么。

### 5.9 Package Goal-to-Guard Demo

Demo 用包裹场景证明方法，而不是证明系统只能做包裹：

```text
用户安全目标：包裹送达后，在用户回家前避免丢失或天气损坏
→ 读取/填写设备清单
→ 匹配门口视觉、HomeBase、家庭状态和通知能力
→ 生成跨设备策略
→ 动态生成家人取件、快递员二次靠近、陌生人拿走、遮挡、离线等测试
→ 至少暴露一次失败
→ 用户/红队质疑触发策略修订
→ 输出可试点 / 有条件试点 / 不建议试点
```

没有企业 Device API 时只能运行 Capability Graph + dry-run，前端必须标注“模拟事件验证”，不能写“已控制真实设备”。

### 5.10 飞书在哪里

飞书不是嵌在网页里的另一个聊天框，而是在飞书软件内通过 Aily/机器人、消息卡片和飞书文档工作：

- Aily 接收模糊研究问题并生成 Brief；
- 飞书卡片推送进度、资料缺口、候选和红队意见；
- 用户在飞书完成 Brief、候选晋级和最终建议三个 Gate；
- 飞书批注转成 RevisionRequest；
- 最终提案、证据目录、限制和审批记录写入飞书文档。

Web 负责复杂证据下钻、设备图、竞品生态矩阵、场景验证和 Trace；飞书负责轻量入口、通知、审批和沉淀。两端读取
同一后端 Project/Checkpoint/Artifact，飞书不能绕过后端 Evidence Gate。

比赛要求至少使用一条飞书 Agent，最适合的是“Research Brief + Human Gate 协作 Agent”，而不是让飞书重新实现
整个研究推理系统。

## 6. 后续后端分支顺序

### 下一分支：`agent/ecosystem-opportunity`

目标：把用户研究、竞品综合、共享 Evidence 和设备能力图转换成多个生态级候选。

必须完成：

- 新建真实 Agent、Prompt、Context Builder、Model Adapter 和 Service；
- 消费最新 advancing 的 UserResearchArtifact、CompetitorArtifact；
- 从 Device Capability Graph 读取证据约束，设备能力未知时保留 hypothesis/gap；
- 动态生成目标 3 个、最多 5 个候选；
- 至少能够表达 `ecosystem_service`，但证据不足时不能硬凑；
- 每个事实性判断引用 Evidence ID；
- 不固定 Guardian Agent、门铃或包裹模板；
- 输出版本化 `EcosystemOpportunityArtifact`；
- 实现已经定义的 `/api/v2` 目标契约对应 `/api/v1` 可运行 Route；
- 暂不接入 LangGraph 主图，先独立真实链路测试，再由 Gate 分支接线。

验收示例：

```text
同一个 Brief，改变用户/竞品 Evidence 或设备能力
→ 候选结构和缺口随证据变化
→ 能力 unknown 时出现 portfolio_gap
→ 无法支持生态服务时允许少于三个候选
→ 不调用固定包裹模板凑数
```

### 后续顺序

```text
1. agent/ecosystem-opportunity
2. workflow/ai-native-ecosystem-gate
3. agent/technical-feasibility
4. agent/security-policy-compiler
5. workflow/security-policy-verification
6. agent/commercial-evaluation-v2
7. agent/redteam-policy-revision
8. demo/package-goal-to-guard
9. integration/feishu-aily
10. backend/e2e-ecosystem-hardening
```

`integration/eufy-device-api` 是可选等待分支：只有企业明确提供授权流、设备列表、事件、动作、HomeBase 能力、隐私
规则和沙箱环境后才做。没有企业接口不阻塞 dry-run Demo，也不能使用假 API 冒充联调。

## 7. 每个后续 Agent 的判断方式

Agent 的语义判断由真实模型 API 完成，但不能只靠 API：

```text
共享 Evidence / 上游 Artifact / Capability Query
→ Context Builder 预算和筛选
→ Model Gateway 调用用户选择的模型
→ 结构化输出
→ 确定性 Validator 校验 Evidence、范围、状态和 ID
→ Artifact Store 版本化保存
→ Gate / Source Recovery / Revision
```

- 模型负责总结、比较、提出假设和解释；
- 后端负责证据资格、引用范围、权限、状态、重复、成本、版本和持久化；
- 技术 Agent 不应仅靠模型常识判断具体设备能力，而要消费 Capability Graph；
- 商业 Agent 不重复猜技术，要消费 Technical Feasibility Artifact；
- 红队必须能够实际改变候选、策略或结论。

## 8. 发布前检查

每个后续分支发布前执行：

```powershell
cd C:\Users\zehao\Desktop\agentinsight-eufy\src\backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest
```

如果 Windows 再次拒绝 pytest 临时目录，使用获批的系统临时目录 `--basetemp` 重跑；不要把权限错误当成业务失败，也
不要为了绕过权限把测试改成不验证真实行为。

还要执行：

```powershell
cd C:\Users\zehao\Desktop\agentinsight-eufy
git diff --check
git status -sb
git diff --stat
```

检查重点：

- `docs/api/openapi.yaml` 可解析；
- Migration 从空库升级到 head；
- 新增 API 与 OpenAPI 字段一致；
- 家庭快照不接收序列号、精确地址和原始视频；
- 其他项目 Evidence 被拒绝；
- 不合格 Evidence 被拒绝；
- conflict 不被覆盖；
- unknown/unavailable 不被模型补造；
- 新项目不再接受旧单品 Research Brief；竞品、资料和现有主图底座测试无回归。

本分支已完成的中文 Commit：

```text
实现证据约束的设备能力图
补充设备能力图接口与迁移测试
完善设备能力图文档和开发交接
```

本分支合并记录：

```text
已切换 main
已执行 merge --no-ff evidence/device-capability-graph
已推送 main
```

GitHub Actions 通过后再开始 `agent/ecosystem-opportunity`。

## 9. 密钥和本地环境

- API Key 只放本地 `.env`，绝不写入本文档、测试、Commit 或聊天截图；
- 当前模型、Tavily 和 OpenCode 的环境变量名称以 `.env.example`/Settings 为准；
- 新账号在同一电脑可以使用现有本地 `.env`，但不应读取或打印 Key；
- 换电脑时通过安全渠道重新配置，不复制聊天中出现过的 Key；
- GitHub 只保存代码、契约和交接文档。

## 10. 交接文件维护规则

以后每完成一个分支都更新本文档：

1. 当前远程 `main` 提交；
2. 已完成能力；
3. 新增真实 API；
4. 测试结果；
5. 下一分支；
6. 新的前端状态或交互；
7. 未解决阻塞；
8. 明确哪些能力仍是目标契约。

聊天记录可以丢失，但仓库内的目标、边界、接口、测试和下一步不能丢失。
