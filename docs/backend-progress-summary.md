# 后端进度与前端适配说明

> 更新时间：2026-08-11
>
> 基线分支：`main`；设备能力图开发状态见 `docs/CODEX_HANDOFF.md`
>
> 基线提交：以 `main` 最新提交为准

## 1. 这份文档解决什么问题

- 当前 `/api/v1` 已经可以真实调用的能力；
- 已完成底层实现、但还没有接入完整 HTTP 业务流程的能力；
- 仍然返回 `501` 或尚未开发的能力；
- 前端当前可以直接开始的工作，以及应该等待后端契约稳定后再做的工作。

前端当前继续使用：

```text
http://localhost:8000/api/v1
```

`docs/api/openapi.yaml` 描述的是 `/api/v2` **目标契约**，不是已经全部上线的接口。前端不能直接把其中的 Demo、Report、Metrics 和飞书接口当成当前可用能力。

## 2. 当前后端做到哪里了

一句话概括：

> 项目生命周期、统一资料链路、用户研究、竞品 A2A 与生态层综合、通用资料恢复、共享 Evidence Retrieval、设备能力图、AI 原生 Research Brief、多轮追问、真实生态机会、AI Native Gate、技术可行性 Agent、Security Policy Compiler、dry-run Policy Verification 和 Commercial Evaluation v2 已经完成；主图会根据验证结果进入商业评估、补研或策略修订。红队、Demo 与飞书仍未完成，因此系统还不能自动完成一整轮 AI 原生生态定义与验证。

### 2.1 已完成并合并到 `main`

| 模块 | 当前能力 | 对前端的意义 |
|---|---|---|
| 项目生命周期 | 创建/查询项目、AI 原生家庭安防生态 Brief 人工审批、状态迁移、持久化事件；旧单品 Brief 被 422 拒绝 | 可以实现项目列表、生态 Brief 确认页和审批面板 |
| Research Brief 追问 v2 | 项目创建前调用用户选择的模型逐轮追问，持久化部分草稿、缺失字段、问题、版本和 Token/成本；确定性校验通过后才返回完整 Brief | 可以实现 Deep Research 模糊输入、聊天式追问、草稿预览和最终确认；不能跳过确认直接研究 |
| SSE 事件 | 历史事件回放、实时事件、断线续传游标、心跳 | 可以实现实时研究时间线和连接状态 |
| Evidence Foundation | Evidence、Collection Job、Claim、去重、跨项目隔离、Claim Gate、失败记录 | 可以实现 Evidence Center 和 Claim-Evidence 关系展示 |
| 共享 Evidence 检索 | 所有现有领域 Agent 共用项目隔离、状态门禁、元数据/词法相关度、来源多样性、字符预算与 Context Hash；产品技术保留精确 Evidence ID 顺序 | 可以实现“Agent 使用了哪些资料”的证据抽屉；当前是可解释词法检索，不应标成向量语义 RAG |
| Source Ingestion | 用户/企业授权文件上传、公开链接登记、项目隔离存储、哈希去重、授权审计、删除与 Collection Job | 可以实现真实资料输入页和资料资产列表 |
| Source Processing | 文档/网页确定性解析；音视频容器探测、标准化音轨、关键帧、衍生产物 Hash；失败/重试/取消、媒体人工复核与受控 Evidence 入湖 | 可以展示网页和媒体处理状态、可回溯片段、保留音轨/帧及审核操作；未配置 ASR/视觉 Connector 时媒体语义阶段明确 blocked |
| Source Routing | 可解释规则、必要时模型辅助、多标签 route、置信度、人工确认/拒绝、模型审计、项目事件 | 可以提供统一资料中心的“自动识别”，用户不再为每个 Agent 重复上传或必须理解 claim_type |
| Source Requirements | 保存目标产品、竞品和研究维度；优先按 Onboarding 准确产品血缘，再结合确认 route、地区和 Evidence 实时计算 `ready/partial/blocked` | 可以实现资料准备清单，避免标题同时提到多个产品时错误归属，并区分“已检测资料”和“已满足 Evidence” |
| Search Discovery | 通过显式注册的 Tavily Search Provider 发现公开候选 URL；项目隔离运行、失败分类、安全去重和域名过滤；结果固定为 `candidate_only` | 可以实现“查找资料”动作和候选来源列表；不能把搜索摘要显示成证据或自动勾选为已满足 |
| Competitor Discovery | 主办方模型从 `competitor_candidate` 搜索运行中提名准确品牌/型号；确定性校验全部 candidate ID、目标重叠和文本依据；版本化 Artifact 停在一次性 Candidate Gate | 可以实现候选竞品审批页；Gate 前不能改写正式范围，确认后刷新资料要求并进入来源接入 |
| Competitor Source Onboarding | 从已 confirm 的 Candidate Gate 自动读取所选 proposal/candidate；原子登记授权 Source Asset 和血缘；提交后自动完成网页处理、Source Routing 和资料要求重评，逐来源隔离失败 | 候选审批后只需确认一次授权；页面通过 Processing、Routing 和 SSE 展示进度，低置信度路由仍需复核，解析/路由成功仍不是 Evidence |
| Innovation Foundation | 事件理解结构、八维评分、红队结果、候选组合门禁、持久化查询 | 可以实现候选机会比较页，不应继续只依赖旧 `Concept` 类型 |
| LangGraph AI 原生主路径 | Brief Gate、并行用户/竞品生态研究、Evidence Readiness、生态机会、AI Native Human Gate、技术可行性、Security Policy Compiler、Policy Verification、Commercial Evaluation v2、Checkpoint、定向修订和 Source Recovery 恢复 | 可以展示真实节点、门禁、策略验证和商业评估状态；商业缺证时暂停补研，完成后等待红队 |
| Agent Runtime Core | Agent Run、Adapter Registry、Artifact Store、超时、取消、错误分类、运行隔离、运行事件 | 可以展示 Agent 状态、错误、Artifact 元数据和运行历史 |
| External CLI Runtime | 固定 Driver 注册、CLI 健康探测、项目/运行隔离目录、输出限制、超时/取消、密钥脱敏、OpenCode Driver | 可以通过 `/runtimes` 展示外部 Agent 是否真实可用；不能把未声明的网站/视频能力标成可用 |
| Model Gateway | 模型目录、项目默认模型、Agent 级覆盖、Prompt 版本、结构化输出、重试、Token/成本审计 | 可以实现模型选择器和 Agent 调用审计展示 |
| 主办方模型路由 | 已接入 GLM 5.2 与 DeepSeek V4 Pro，并完成真实联网冒烟测试 | 前端只使用 `/models` 返回的 `model_id`，不接触 API Key |
| 用户研究 Agent | 消费受控 Evidence Context，输出带 Evidence IDs 的事件链、痛点和未满足需求 | 可以启动真实用户研究并展示证据覆盖、未知项和模型审计 |
| 竞品 A2A Foundation | 竞品主管、三类 EvidenceRequest、并行专家网关、A2A Task 审计、超时和定向恢复 | 可以按 SSE 事件展示三条真实专家泳道；证据不足的专家会返回自己的 blocked 与补研问题 |
| 竞品官方产品专家 | 从受控官方 Evidence 中提取产品身份、能力、规格、兼容性、限制和未知项；确定性校验范围与引用 | 可以展示官方专家的真实结构化结果和证据覆盖；不能把父级 partial 当成完整竞品结论 |
| 竞品资料发现与片段 Evidence | 按准确产品和研究维度发现候选资料，经 Gate、网页处理、路由、片段审核后晋级带血缘 Evidence | 可以统一展示“候选→已授权→已解析→已审核→可供 Agent 使用”，不能把搜索摘要直接当证据 |
| 竞品价格渠道专家 | 从目标地区的受控价格、库存、卖家与促销 Evidence 中输出时间化价格和渠道观察；确定性校验产品、地区、Claim 类型、采集时间与引用 | 可以展示价格/库存快照、渠道和 Evidence IDs；不得显示为永久价、全网最低价或实时库存 |
| 竞品用户评价专家 | 从受控 user_opinion Evidence 中提炼正负体验、事件、影响、矛盾与样本限制；重复主题由后端按 Evidence 和独立来源计算 | 可以展示单条反馈和跨来源重复主题；不得把单个作者或单一页面显示成普遍用户结论 |
| 竞品产品事实综合 | 三个专家均有发现后先调用产品事实综合模型，保留逐产品优缺点、权衡和准确 Evidence 血缘，供生态层继续使用 | 可以下钻查看生态结论来自哪些具体设备、价格或用户评价；该层不再直接作为新项目最终竞品结论 |
| 竞品生态综合与证据审计 | 在产品事实之上调用生态综合模型，按 Brief 中目标/对照生态生成 12 维能力矩阵；后端审计生态范围、产品映射、专家维度和 Evidence | 可以展示 Ring、Google Nest、Arlo、eufy 等生态矩阵；未覆盖维度必须显示 `unknown` 与补研问题，不能显示成“竞品没有” |
| 竞品主路径桥接 | 用户研究与竞品生态 Artifact 并行汇合后生成 `ResearchHandoff`；完整结果为 `ready`，经过审计的缺口结果为 `ready_with_gaps`，无效结果定向补研 | 可以展示研究交接状态、生态/产品范围、12 维状态和缺口；下一步生态机会 Agent 消费同一交接 |
| 旧单产品链路清理 | Product Technical v1 的 API、Adapter、Prompt、Service、配置与测试已经删除；只保留旧 Checkpoint 交接字段的读取别名 | 前端不得再调用旧路径；所有机会生成、候选查看和补研都使用生态机会链路 |
| 生态机会资料恢复 | 把生态候选的 `portfolio_gaps` 转换为结构化补充字段；用户确认后的内容生成带血缘 Evidence，并定向恢复生态机会 Agent | 可以按 `gap_id` 弹出“当前缺什么”的填写框，展示受影响机会和定向恢复范围；不要求用户盲目更换网站，也不会把填写内容伪装成官网证据 |
| 生态机会 Agent 与 AI Native Gate | 真实模型基于用户、竞品生态、Evidence 和设备能力图动态生成候选；确定性 Gate 阻止普通通知/固定规则包装，语义问题交给 Human Gate | 前端可以展示真实候选、八项检查、补研/修订/淘汰；不能把通过 AI Native Gate 写成技术可行或可上架 |
| 技术可行性 Agent | 模型拆解设备、数据、API、部署、性能、隐私、权限与韧性要求；后端以 Capability Graph 和 Evidence 计算四类 verdict，并接入主图定向补研 | 可以展示每个已选机会的技术条件、设备覆盖、Evidence、Gap 和 Demo 边界；`unknown` 不是“不支持”，通过技术验证也不是“可上架” |
| Security Policy Compiler | 模型生成策略意图；后端校验授权信号、设备角色、干预权限和 Evidence，并确定性生成版本化 dry-run DSL、五类降级与安全不变量 | 可以展示跨设备状态、风险规则、干预阶梯、失败降级和版本差异；不能控制真实设备，尚未证明策略有效 |
| Security Policy Verification | 从已编译 DSL 生成风险规则和五类 fallback 场景，运行确定性断言，并接受受策略范围约束的用户场景 | 可以展示场景、trace、命中规则、风险、动作、失败和 Gap；只证明当前 dry-run 场景行为，不代表真实部署或商业可行 |
| Commercial Evaluation v2 | 分别判断用户价值、商业假设与交付运营条件；交付结论消费技术和策略验证结果，最终 recommendation 由后端计算 | 可以展示四类 recommendation、Evidence 下钻、商业假设与补研 Gap；没有商业总分，也不承诺上架或收益 |
| 设备能力图 | 保存带 Evidence 的厂商设备能力、用户授权家庭快照和 `available/unavailable/unknown/conflict` 确定性查询；不保存家庭视频或序列号 | 可以实现“方案需要什么能力、已有设备能否支撑、还缺什么”的设备覆盖页；企业 API 未接入时不得显示实时设备状态 |

### 2.2 已完成底座、但还没有形成完整业务运行

以下能力在内部服务和自动化测试中已经成立，但前端不能误认为“创建项目后就会自动生成完整报告”：

1. LangGraph 主图能够在测试 Runtime 下完成并行节点、三次暂停和 Checkpoint 恢复。
2. Agent Runtime 能够调用显式注册的 Adapter，并保存 Agent Run 与版本化 Artifact。
3. `InternalModelAgentAdapter` 能够通过 Model Gateway 调用真实模型。
4. `ExternalCliAgentAdapter` 能够通过 OpenCode 调用主办方模型，并返回结构化 `ResearchArtifact`。
5. Source Processing 可以解析授权文件/网页，并真实解码音视频；媒体 Connector 输出会保持 `derived`，人工复核后才能通过受控服务进入 Evidence Lake。
6. Evidence 和 Innovation 服务可以保存、校验和查询真实持久化记录。
7. 竞品官方产品专家能够通过项目模型策略调用 GLM 5.2 或 DeepSeek V4 Pro，输出带 Evidence IDs 的结构化官方资料结果。
8. 已确认的多标签 Source Route 可以限定领域 Agent 的 Evidence Context；分类本身不会自动生成 Evidence。
9. 资料准备度可以在不调用模型的情况下识别竞品范围缺失、准确型号缺失、资料处理失败、路由/Evidence 未完成和价格地区不匹配。
10. 竞品候选发现 Agent 可以消费真实 Tavily 结果，经 Model Gateway 输出 `completed/partial/blocked` Artifact；人工确认前保持零 Evidence、零正式竞品变更。
11. 已确认竞品候选可以批量接入 Source Asset，并保存 Artifact、Decision、Proposal、Candidate、准确产品和 Source Asset 的结构化血缘；接入完成仍保持零 Evidence。
12. 竞品资料发现可以按准确产品和 `official_product/price_channel/user_review` 维度生成搜索候选，经 Gate 后进入既有网页处理链路。
13. Fragment Evidence Pipeline 只允许已验证片段、已确认路由和准确产品血缘晋级为 Evidence，并保留人工决定。
14. 价格渠道专家能够通过项目模型策略调用 GLM 5.2 或 DeepSeek V4 Pro，输出带 Evidence IDs、地区和采集时间边界的结构化价格渠道结果。
15. 竞品用户评价专家能够调用相同模型策略，严格消费准确产品的 `user_opinion`，并由确定性代码区分单一报告和跨来源重复主题。
16. 竞品主管能够在三个专家均产生发现后调用综合模型，并确定性拒绝虚构 Evidence、跨产品引用和跨专家维度引用；资料不足时不调用综合模型。
17. LangGraph 能够把用户研究与竞品生态综合写入强类型 `ResearchHandoff`；经过审计的 partial 缺口可进入生态机会阶段，无效竞品结果只重跑竞品节点，Checkpoint 不重复执行用户研究。
18. 生态机会 Adapter 已注册到统一 Runtime 和 Model Gateway，主路径与独立 HTTP 用例消费同一上游 Artifact，输出版本化 `ecosystem_opportunity_portfolio`。
19. 生态机会 Artifact 的补研缺口具有稳定 ID；可创建通用 Source Recovery、生成 `user_declaration` Evidence，并把已解决 Evidence 注入下一版生态机会上下文。
20. 用户研究、三个竞品专家和生态机会 Context Builder 使用共享 Evidence Retrieval；后续商业与红队可以复用同一接口，不再建立各自知识副本。
21. 生态机会契约和真实 Agent 已经完成，候选随用户、竞品、Evidence 和设备能力图变化，证据不足时保留真实数量与稳定 Gap。
22. Device Capability Graph 能够把厂商通用能力与家庭实例分开，拒绝不合格或跨项目 Evidence，保留冲突，并确定性回答方案能力覆盖。
23. 新 Research Brief 已删除单品式字段，强制表达生态、安全目标、信号授权、隐私/干预边界和验证期望；全部项目创建测试已迁移。
24. Research Brief Clarifier v2 已能通过 Model Gateway 动态追问；模型字段必须引用用户消息，完整性由后端检查，完成后仍进入现有 Brief Gate。
25. 竞品生态链路复用候选发现、三个 A2A 事实专家和产品事实综合，再调用生态综合模型；确定性后端生成 12 维覆盖矩阵，拒绝跨生态、跨产品、跨专家 Evidence，并把 v2 Artifact 投影进 `ResearchHandoff`。
26. AI Native Gate 不调用模型，确定性检查生态范围、跨设备闭环、AI removal test、职责分离、修订、隐私/fallback、授权和部署前验证；语义判断暂停 Human Gate，补研恢复只重跑生态机会。
27. Technical Feasibility 已注册到真实 Model Gateway 与 Runtime；只处理 Human Gate 选择的机会，模型不能写最终 verdict，设备能力匹配和晋级由后端确定性计算。
28. 主图在技术证据不足时进入统一 Source Recovery，补证后只重跑技术 Agent；至少一个 `demo_feasible` 或 `conditionally_feasible` 才进入 `awaiting_security_policy`。
29. Commercial Evaluation v2 已接入 Model Gateway、Runtime、共享 Evidence 和主图；用户价值、商业模式与交付运营独立输出，缺证时只重跑商业 Agent。

当前仍缺少：

- HTTP 项目生命周期与 LangGraph 完整启动/恢复的生产接线；
- 红队 Prompt、用户质疑与定向策略修订；
- 真实 ASR 和视觉模型 Connector（当前主办方两个文本模型不能替代）；
- 最终报告、Package Risk Demo 和飞书集成。

生产环境没有注册业务 Prompt 或真实业务 Adapter 时会明确失败，不会用 Mock 结果冒充调研完成。

## 3. 当前真实可用的 `/api/v1` 接口

| 方法 | 路径 | 状态 | 前端用途 |
|---|---|---|---|
| `GET` | `/health` | 可用 | 服务健康状态 |
| `GET` | `/models` | 可用 | 模型选择器；返回安全模型目录和凭据可用状态 |
| `GET` | `/runtimes` | 可用 | 外部 Agent 选择器；返回 CLI、凭据、版本和已验证能力状态，不返回本机路径与密钥信息 |
| `POST` | `/research-brief-clarifications` | 可用 | 提交模糊研究目标和可选模型，开始项目外多轮追问 |
| `GET` | `/research-brief-clarifications/{session_id}` | 可用 | 恢复对话、部分 Brief、缺失字段、问题和模型用量 |
| `POST` | `/research-brief-clarifications/{session_id}/messages` | 可用 | 提交带版本的用户回答；只有完整校验通过才返回可确认 Brief |
| `GET` | `/projects` | 可用 | 项目列表 |
| `POST` | `/projects` | 可用 | 创建项目，提交 Brief 和可选模型策略 |
| `GET` | `/projects/{project_id}` | 可用 | 项目详情、进度和待审批信息 |
| `GET` | `/projects/{project_id}/agents` | 可用 | Agent Run 列表与模型调用审计摘要 |
| `POST` | `/projects/{project_id}/agents/competitor-ecosystem` | 可用 | 运行三个竞品事实专家、产品事实综合和生态综合，返回带 Evidence 审计的 12 维生态矩阵 |
| `GET` | `/projects/{project_id}/agents/competitor-ecosystem/artifacts` | 可用 | 查询版本化竞品生态 Artifact、覆盖矩阵、未知项与补研问题 |
| `POST` | `/projects/{project_id}/agents/ecosystem-opportunity` | 可用 | 运行生态机会 Agent；动态生成设备功能、设备产品或生态服务候选，证据不足时保留真实数量与 Gap |
| `GET` | `/projects/{project_id}/agents/ecosystem-opportunity/artifacts` | 可用 | 查询版本化生态机会、AI Native 结构、Evidence IDs 和补研问题 |
| `POST` | `/projects/{project_id}/agents/commercial-evaluation-v2` | 可用 | 运行证据约束的生态商业评估；不计算商业总分，不代表上架或收益保证 |
| `GET` | `/projects/{project_id}/agents/commercial-evaluation-v2/artifacts` | 可用 | 查询用户价值、商业假设、交付运营、recommendation 和补研 Gap 历史版本 |
| `POST` | `/projects/{project_id}/agents/ecosystem_opportunity/artifacts/{artifact_id}/source-recovery` | 可用 | 通过领域 Agent 通用接口把生态机会缺口转换为前端补充弹窗，并保存定向恢复血缘 |
| `GET` | `/projects/{project_id}/events` | 可用 | SSE 实时事件和历史回放 |
| `POST` | `/projects/{project_id}/decisions` | 可用 | 提交当前 Human Gate 决定 |
| `GET` | `/projects/{project_id}/source-requirements` | 可用 | 实时查询目标/竞品范围和各研究维度的资料准备度、缺口与补充动作 |
| `PUT` | `/projects/{project_id}/source-requirements/scope` | 可用 | 保存目标产品、竞品、研究维度及 actor/reason，并立即重新评估 |
| `POST` | `/projects/{project_id}/source-discovery/searches` | 可用 | 调用已注册搜索 Provider；返回候选线索或可审计的 blocked/failed 状态，不创建 Evidence |
| `GET` | `/projects/{project_id}/source-discovery/searches` | 可用 | 查询项目内搜索发现历史和候选来源 |
| `GET` | `/projects/{project_id}/source-discovery/searches/{search_discovery_run_id}` | 可用 | 查询单次搜索状态、错误分类和 `candidate_only` 结果 |
| `POST` | `/projects/{project_id}/agents/competitor-discovery` | 可用 | 消费成功的竞品搜索运行，调用项目的竞品研究模型，返回版本化待审批候选 Artifact |
| `GET` | `/projects/{project_id}/agents/competitor-discovery/artifacts` | 可用 | 查询候选发现历史版本、覆盖率、未知项和 Candidate Gate 状态 |
| `POST` | `/projects/{project_id}/agents/competitor-discovery/artifacts/{artifact_id}/decision` | 可用 | 确认、拒绝或要求返工；只有确认的 proposal 会更新正式竞品范围 |
| `POST` | `/projects/{project_id}/competitor-source-onboardings` | 可用 | 在确认公开资料授权后，把 Gate 选择的候选 URL 原子登记为 Source Asset；重复 Artifact 返回原批次 |
| `GET` | `/projects/{project_id}/competitor-source-onboardings` | 可用 | 查询项目内接入批次、候选到 Source Asset 的血缘和创建/复用计数 |
| `POST` | `/projects/{project_id}/sources/files` | 可用 | 上传用户或企业授权的 PDF、文本、DOCX、CSV、JSON、图片、音频或视频 |
| `POST` | `/projects/{project_id}/sources/links` | 可用 | 登记用户指定的公开 HTTP/HTTPS 链接；请求本身不会抓取网页 |
| `GET` | `/projects/{project_id}/sources` | 可用 | 按类型和状态查询项目原始资料 |
| `GET` | `/projects/{project_id}/sources/{source_asset_id}` | 可用 | 查询资料元数据和待解析任务 ID |
| `GET` | `/projects/{project_id}/sources/{source_asset_id}/routing` | 可用 | 查询多标签分类建议、确认 route 和模型审计 |
| `POST` | `/projects/{project_id}/sources/{source_asset_id}/routing/analyze` | 可用 | 运行确定性规则，必要时调用项目模型补充分类 |
| `POST` | `/projects/{project_id}/sources/{source_asset_id}/routing/decision` | 可用 | 人工确认、修改或拒绝路由建议 |
| `DELETE` | `/projects/{project_id}/sources/{source_asset_id}` | 可用 | 删除文件内容、阻止待运行任务并保留最小审计状态 |
| `GET` | `/projects/{project_id}/sources/{source_asset_id}/processing` | 可用 | 查询 Collection Job、进度、错误与 Parsed Artifact |
| `POST` | `/projects/{project_id}/sources/{source_asset_id}/processing` | 可用 | 在隔离工作区同步执行有界确定性解析；重复成功请求保持幂等 |
| `POST` | `/projects/{project_id}/sources/{source_asset_id}/processing/retry` | 可用 | 重试 failed、blocked 或 cancelled 任务并累计尝试次数 |
| `POST` | `/projects/{project_id}/sources/{source_asset_id}/processing/cancel` | 可用 | 在开始执行前取消 queued 任务 |
| `GET` | `/projects/{project_id}/sources/{source_asset_id}/fragments` | 可用 | 分页查询通过原文复核的定位片段 |
| `POST` | `/projects/{project_id}/sources/{source_asset_id}/fragments/{source_fragment_id}/review` | 可用 | 对照保留媒体审核 derived 片段；只有 verified 可进入 Evidence |
| `GET` | `/projects/{project_id}/sources/{source_asset_id}/media-artifacts/{media_artifact_id}` | 可用 | 项目内读取供审核的 WAV 音轨或 PNG 关键帧，不暴露本地路径 |
| `GET` | `/projects/{project_id}/evidence` | 可用 | Evidence 分页、状态/来源筛选 |
| `POST` | `/projects/{project_id}/evidence/retrievals` | 可用 | 按 Agent 问题与元数据生成项目隔离 Evidence Context，返回相关度、匹配原因和 Context Hash |
| `GET` | `/projects/{project_id}/claims` | 可用 | Claim 与支持/反对 Evidence IDs |
| `GET` | `/projects/{project_id}/innovations` | 可用 | 候选机会、事件理解、评分和红队结果 |
| `POST/GET` | `/projects/{project_id}/device-capabilities/catalog` | 可用 | 登记或查询带 Evidence 的厂商设备能力目录 |
| `GET/PUT/DELETE` | `/projects/{project_id}/device-capabilities/catalog/{catalog_device_id}` | 可用 | 查询、替换或删除未被家庭快照引用的目录设备 |
| `PUT/GET` | `/projects/{project_id}/device-capabilities/household-snapshot` | 可用 | 保存新版本或读取当前用户授权家庭设备快照 |
| `POST` | `/projects/{project_id}/device-capabilities/queries` | 可用 | 确定性查询方案所需能力的 available/unavailable/unknown/conflict 与 Evidence IDs |

查询接口只返回数据库中已经存在的记录。证据不足时会返回空列表或明确状态，不会自动生成占位 Evidence、Claim 或 Innovation。

### 3.1 当前仍是骨架的接口

| 方法 | 路径 | 当前行为 | 前端处理方式 |
|---|---|---|---|
| `GET` | `/projects/{project_id}/concepts` | `501 Not Implemented` | 新页面改用 `/innovations`；旧 Concept 页面只作为待迁移 UI |
| `GET` | `/projects/{project_id}/report` | `501 Not Implemented` | 展示“报告尚未生成”，不要把 Mock 报告标成真实结果 |
| `GET` | `/projects/{project_id}/metrics` | `501 Not Implemented` | 展示空状态或明确的演示数据标识 |

以下目标能力尚无当前 `/api/v1` 生产接口：

- Package Risk Demo Result；
- 最终报告和方法对照指标；
- 飞书 Aily Skills、审批卡片和文档沉淀；
- 外部 Runtime 任务启动/取消、A2A 子任务查询/控制和真实资料解析任务控制。

## 4. 前端需要立即对齐的数据契约

### 4.1 模型选择

前端应先调用：

```http
GET /api/v1/models
```

前端只展示后端返回的：

- `model_id`
- `display_name`
- `provider`
- `capabilities`
- `credential_available`
- `default_model_id`

创建项目时可以提交：

```json
{
  "brief": {
    "question": "调研 eufy 家庭安防未来产品机会",
    "category": "家庭安防",
    "target_user": "北美家庭安防用户",
    "region": "US",
    "scenarios": ["门前包裹", "车库门", "陌生人徘徊"],
    "constraints": [],
    "focus_dimensions": []
  },
  "model_selection": {
    "default_model_id": "anker:glm-5.2",
    "agent_overrides": {}
  }
}
```

模型 ID 必须来自 `/models`，不要在前端硬编码 Provider 内部模型名，更不能保存或请求 API Key。

### 4.2 外部 Runtime 选择

前端应调用：

```http
GET /api/v1/runtimes
```

当前目录只包含 `opencode`，并区分 `enabled`、`executable_available`、`credential_available` 和最终 `available`。前端只能允许用户选择 `available=true` 的 Runtime；`capabilities` 目前只声明 `text`、`structured_output` 和 `local_files`。网页获取和音视频预处理来自 Source Processing 的独立 Connector，不是 OpenCode Runtime capability；当前没有生产 ASR/视觉 Connector，所以不能标记“语音转写/画面理解可用”。`unavailable_reason` 应直接映射成“未安装”“缺凭据”“探测失败”或“已禁用”，不要静默回退到假结果。

### 4.3 `Project` 类型

当前后端 `Project` 比前端类型多一个字段：

```text
model_selection: ModelSelection | null
```

前端应保留该字段，用于项目详情和模型审计展示。

### 4.4 `AgentRun` 类型

后端支持的状态比当前前端类型更多：

```text
pending
queued
running
waiting
completed
partial
failed
blocked
needs_revision
cancelled
```

后端还会返回：

```text
task_id
quality_score
evidence_ids
unknowns
model_id
model_provider
prompt_key
prompt_version
input_tokens
output_tokens
estimated_cost_microusd
```

前端的 Agent 历史、错误状态和成本展示可以直接基于这些字段设计。

### 4.5 `SourceAsset` 类型

前端资料输入页可以直接接入 `/sources/files` 和 `/sources/links`。文件上传使用 `multipart/form-data`，必须提交：

```text
file
authorization_basis
authorization_confirmed=true
authorized_by
purpose
```

链接登记使用 JSON，除授权字段外还需提交 `source_url` 和 `display_name`。`authorization_basis` 只能是 `user_owned`、`enterprise_authorized` 或 `publicly_available`。

响应中的 `collection_job_id` 表示已经建立待解析任务。前端可以调用 `POST /sources/{source_asset_id}/processing` 执行当前有界同步处理，通过 `GET /processing` 查询状态，通过 `/processing/retry` 和 `/processing/cancel` 处理失败或排队任务，并从 `GET /fragments` 展示带页码、行号、行记录或字符范围的原文片段。

当前确定性 Parser 支持 TXT、Markdown、CSV、JSON、可提取文本的 PDF 和授权公开 HTML。网页处理成功后，`job.result` 会提供 URL、HTTP 和快照 Hash 元数据；网页 locator 为 `kind=web`。

音视频处理使用 PyAV 自带 FFmpeg 库，不要求用户额外安装 `ffmpeg` 命令。`job.result.media_manifest` 提供容器、时长、流以及音轨/关键帧的安全元数据。没有 ASR/视觉 Connector 时任务返回 `MEDIA_UNDERSTANDING_CONNECTOR_NOT_CONFIGURED`，但保留媒体审核产物；前端可以展示“预处理完成、语义分析待配置”。有 Connector 时，转写 locator 为 `media_time`，画面描述 locator 为 `media_frame`，并包含产物 Hash、Connector、模型和置信度。它们最初为 `derived`，必须调用 review 接口确认后才能晋级 Evidence。

DOCX 和独立图片仍在没有专用 Connector 时返回 `blocked`。`SourceAsset` 不是 Evidence；只有 `verified` Source Fragment 才能通过内部受控服务进入 Evidence Lake。文件系统路径和 API Key 都不会通过接口返回。

网页输入必须由用户登记并确认授权。前端不提供“全网自动爬取”开关，也不展示验证码、Cloudflare 绕过或登录 Cookie 配置。生产部署仍应通过网络出口策略禁止后端访问内网地址，形成应用层 SSRF 校验之外的第二道边界。

### 4.6 `Evidence` 类型

当前前端类型与真实后端存在字段名差异：

| 前端旧字段 | 后端真实字段 |
|---|---|
| `excerpt` | `original_excerpt` |
| `captured_at` | `collected_at` |

后端还返回 `source_domain`、`source_asset_id`、`source_fragment_id`、`source_locator`、`claim_type`、`product`、`region`、`user_segment`、`published_at`、`authority_score`、`recency_score` 和 `diversity_score`。授权上传文件形成的 Evidence 没有公开 URL，因此 `source_url` 和 `source_domain` 可以为 `null`，前端应改为展示 Source Asset 与定位信息，不能伪造外链。

### 4.7 `Claim` 类型

除现有字段外，后端还返回：

```text
claim_type
scope
```

Claim 状态包括 `proposed`、`supported`、`disputed`、`missing_evidence`、`rejected` 和 `unknown`。

### 4.8 使用 `Innovation` 替代旧 `Concept`

当前真实候选接口是：

```http
GET /api/v1/projects/{project_id}/innovations
```

`Innovation` 包含：

- 目标用户和问题定义；
- `Event → State → Context → Inference → Risk/Value → Action`；
- 至少两个 Context Signals；
- 八维评分、权重、理由和 Evidence IDs；
- 红队严重度、风险、降分和决定；
- 最终分数和候选状态。

候选比较页应围绕 `Innovation` 设计，旧 `/concepts` 不应继续作为长期契约。

### 4.9 SSE 当前行为

当前 v1 后端会把 `event_type` 同时作为 SSE 的命名事件类型，并在 `data` 中发送完整 `ProjectEvent` JSON。

前端目前只设置了 `EventSource.onmessage`，可能收不到命名事件。适配时需要：

1. 为已知事件使用 `addEventListener(eventType, handler)`；
2. 保留 `onmessage` 作为普通消息兼容；
3. 按 `event_id` 去重，并按 `sequence_number` 排序；
4. UI 分开显示 `connecting`、`open`、`reconnecting` 和 `fallback`；
5. 断线恢复后不要清空已经收到的事件。

代码中已经定义的事件包括（是否出现取决于对应模块是否已接入当前项目运行）：

```text
project_created
project_status_changed
agent_status_changed
agent_started
agent_completed
agent_failed
agent_timed_out
agent_cancelled
evidence_added
evidence_collection_failed
source_asset_created
source_asset_deleted
source_asset_restored
claim_evaluated
innovation_scored
red_team_reviewed
workflow_gate_pending
workflow_gate_decided
workflow_finished
```

### 4.10 网页/媒体失败后的资料恢复

当前后端已经提供：

```http
GET  /api/v1/projects/{project_id}/source-recoveries
POST /api/v1/projects/{project_id}/source-recoveries
GET  /api/v1/projects/{project_id}/source-recoveries/{source_recovery_id}
POST /api/v1/projects/{project_id}/source-recoveries/{source_recovery_id}/submissions
POST /api/v1/projects/{project_id}/source-recoveries/{source_recovery_id}/decisions
```

网页或媒体失败、或有效信息不足时，前端可以用创建接口获得 `reason_code`、
`requested_fields`、`current_assessment` 和 `resume_directive`，直接展示“补充缺失信息”弹窗。
用户内容会以 `user_input` Source Asset 和 `user_declaration` Evidence 接回现有证据链，不会伪装
成原网页。资料补齐后返回 `targeted_retry`；用户也可以明确选择带缺口继续。

竞品缺口由 Source Requirements 自动生成字段；其他领域 Agent 可以由工作流主管传入
`missing_questions` 与 `affected_agent_types`，因此恢复能力不依赖竞品专用 Requirement。

前端需要新增 Source Recovery Client、恢复弹窗与以下状态展示：

```text
waiting_for_user_input
needs_more_information
resolved
proceeding_with_gaps
cancelled
```

## 5. 建议前端现在并行完成的工作

### P0：先完成真实接口适配

1. 增加 `/models` Client、Hook 和模型选择器。
2. 在 `ProjectCreateInput` 和 `Project` 中加入 `model_selection`。
3. 补齐 `AgentRunStatus` 与 Agent 审计字段。
4. 修正 Evidence 字段名，补齐 Claim 字段。
5. 新增 `Innovation` Type、Client 和候选比较 UI，逐步替代旧 Concept。
6. 修复 SSE 命名事件监听。
7. 对真实接口的 `404/409/422/500/501` 显示明确错误，不要全部静默回退 Mock。
8. 增加资料上传/链接登记页，显示授权依据、文件类型、大小、解析任务状态和删除操作。

### P1：可以先设计、等待真实数据接入

1. Deep Research 输入和 Brief 确认页面。
2. Agent 运行时间线、并行节点和错误恢复展示。
3. Source Asset 与 Evidence 分层展示：前者是待解析原始资料，后者是通过校验的研究证据。
4. Innovation 候选竞技场、评分雷达和红队意见。
5. 三个 Human Gate 的审批面板。
6. Package Risk 交互 Demo 原型。

这些页面可以使用明确标识为 `DEMO SAMPLE` 的展示数据完成布局，但不能在 UI 中把它们表示为后端真实研究结果。

## 6. 本地联调

### 后端

```powershell
cd src/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.main
```

后端地址：

```text
Swagger: http://localhost:8000/docs
Health:  http://localhost:8000/api/v1/health
Models:  http://localhost:8000/api/v1/models
```

### 前端

```powershell
npm install
npm run dev --workspace src/frontend
```

前端环境变量：

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 7. 验证状态与下一步后端计划

最近一次完整验证状态；真实联网记录沿用此前已经完成的受控测试：

```text
技术可行性 Agent 合并前全量 Pytest：330 passed，1 个第三方 Starlette TestClient 弃用警告

Security Policy Verification 合并前全量 Pytest：345 passed，1 个第三方 Starlette TestClient 弃用警告
Commercial Evaluation v2 合并前全量 Pytest：353 passed，1 个第三方 Starlette TestClient 弃用警告
ruff: 全量通过
mypy: 通过（244 个 app 源文件）
前端：ESLint 与生产构建通过
Alembic: 当前迁移头为 0019_device_capability_graph；内存数据库从空库升级到 head 并降级到 0018 通过
OpenAPI: 3.1 YAML 解析通过
git diff --check: 通过
真实模型：GLM 5.2 与 DeepSeek V4 Pro 基础探针、资料路由及官方产品专家完整网页链路冒烟测试通过
价格渠道真实链路：同一授权 eufy 商品页经确定性 HTML 解析得到 372 个片段并审核晋级 2 条 Evidence；GLM 5.2 专家 completed（质量分 90），DeepSeek V4 Pro 返回契约有效的 partial（质量分 75），两次模型调用均 completed
用户评价真实链路：公开 E340 第一人称实测页解析得到 377 个片段，人工式审核晋级 1 条 user_opinion；GLM 5.2 输出 4 个 single_report 主题并在首次结构化失败后重试成功，DeepSeek V4 Pro 一次完成并输出 2 个 single_report 主题；两者都按样本门禁保持 partial，没有伪造重复主题
竞品综合真实模型契约链路：DeepSeek V4 Pro 完成官方产品、价格渠道、用户评价和综合共 4 次真实调用，最终 Artifact completed，5 条 Evidence 通过审计并生成 1 条待产品 Agent 验证的机会信号；GLM 5.2 在三个专家完成后的综合调用遇到主办方 Provider unavailable，系统按失败处理且未生成伪结论
外部 Runtime：OpenCode 1.18.15 + GLM 5.2 结构化 ResearchArtifact 冒烟测试通过
竞品发现与接入：真实 Tavily 返回 5 条 Ring 候选，DeepSeek V4 Pro 确认 Battery Doorbell Pro (2nd Gen)；HTTP 候选经逐跳 robots/页面安全校验跳转到 HTTPS，网页解析成功，自动确认 official_product + price_channel 路由，资料要求重评为 partial，Evidence 保持为 0
```

新方向接下来的后端开发顺序：

```text
Ecosystem Opportunity Contract（已完成）
→ Device Capability Graph（已完成并合并）
→ AI-native Home-safety Research Scope（已完成）
→ Ecosystem Opportunity Agent（已完成）
→ AI Native Ecosystem Gate（已完成）
→ Legacy Single-product Path Cleanup（已完成）
→ Technical Feasibility Agent（已完成）
→ Security Policy Compiler（已完成）
→ Security Policy Verification（已完成）
→ Commercial Evaluation v2（已完成）
→ Red Team Policy Revision
→ Package Goal-to-Guard Demo
→ Feishu Aily Integration
→ E2E Ecosystem Hardening
```
