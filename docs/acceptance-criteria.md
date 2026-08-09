# MVP Acceptance Criteria

## AC-03A 用户研究 Agent 证据链

用户研究 Agent 只能读取当前项目中状态为 `verified` 或
`partially_verified` 的 Evidence。模型输出中的每个 Evidence ID 必须属于本次受控
Evidence Context；痛点和未满足需求必须至少引用一条 `user_opinion` Evidence。
只有具备事件链、痛点、未满足需求、至少两个独立来源且没有高严重度补研缺口时，
Artifact 才能标记为 `completed`。证据不足时必须返回 `partial` 或 `blocked`，不得把
厂商声明改写成用户感受。

自动化映射：

- `tests/unit/test_user_research_contracts.py`
- `tests/integration/test_user_research_context.py`
- `tests/integration/test_user_research_agent.py`
- `tests/integration/test_user_research_api.py`

## AC-03B 竞品 A2A 运行底座

竞品主管必须把同一竞品研究任务拆分为官方产品、价格渠道和用户评价三个独立
`EvidenceRequest`，并并行交给显式绑定的专家 Adapter。每个专家任务保存独立的
`A2A Task`、attempt、trace、状态、错误类别和 Evidence IDs。专家未绑定时必须返回
`blocked`，不得生成占位竞品结论；专家产生的每个事实发现都必须引用本次受控
Evidence Context 中允许类型的 Evidence ID。

任一已绑定专家失败时，竞品主管本轮不得生成成功 Artifact。再次运行相同输入时，
已完成专家结果必须复用，只重跑失败的专家；输入 Evidence Context 或任务范围发生变化
时不得复用旧结果。该底座只做任务拆分、运行审计和确定性聚合，不包含真实专家 Prompt、
竞品能力矩阵或差异化结论。

自动化映射：

- `tests/unit/test_competitor_a2a_contracts.py`
- `tests/integration/test_competitor_a2a_gateway.py`
- `tests/integration/test_competitor_a2a_supervisor.py`
- `tests/integration/test_runtime_langgraph_integration.py`

## AC-03C 竞品官方产品专家

官方产品专家只能读取当前项目中状态为 `verified` 或 `partially_verified`，且 Claim 类型为
`vendor_claim` 或 `fact` 的受控 Evidence。模型输出中的摘要、产品身份和每项官方事实都
必须引用本次 Evidence Context 中的 Evidence ID；产品范围必须与主管的
`EvidenceRequest` 完全一致。

系统必须把产品能力、规格、兼容性、限制和可用性输出为结构化记录，并保留矛盾、未知项
和补研问题。“未在现有官方资料中找到”只能形成未知项，不能推断为“不支持”。引用越界、
范围替换或 Schema 无效时任务失败；没有合格证据时任务 `blocked`；证据覆盖不足时任务
`partial`。质量状态与证据覆盖由确定性代码计算，模型不得自行声明通过。

自动化映射：

- `tests/unit/test_official_product_agent_contracts.py`
- `tests/integration/test_official_product_agent.py`
- `tests/integration/test_competitor_a2a_gateway.py`
- 可重复真实冒烟：`scripts/smoke_official_product_live.py`

## AC-03D 竞品价格渠道专家

价格渠道专家只能读取当前项目中状态为 `verified` 或 `partially_verified`、来源资料已确认
路由到 `price_channel`、地区与 Research Brief 一致，且 Claim 类型属于
`price_observation`、`channel_availability`、`seller_information` 或 `promotion` 的 Evidence。
模型不得联网、搜索或引用训练知识，也不得把搜索摘要、未审核网页片段或其他地区价格作为
价格事实。

每条价格观察必须绑定主管请求中的准确产品、币种、地区、渠道、价格类型和 Evidence IDs；
观察时间范围由后端根据 Evidence 的采集时间确定，模型不得自行声称“当前最低价”。促销、
会员价、套装价、起售价和常规价必须分开记录，缺少变体、卖家、时间或促销条件时必须形成
未知项或补研问题。渠道可用性与价格观察分别建模，`listed` 不得改写成 `in_stock`。

确定性 Validator 必须拒绝越界 Evidence、错产品、错地区、错误 Claim 类型、非正价格、重复
记录和缺少时间血缘的事实发现。没有合格证据时返回 `blocked`；产品、独立来源、价格与渠道
覆盖不足或存在高严重度缺口时返回 `partial`；只有完整满足门禁时才允许 `completed`。父级
竞品主管必须真实绑定该专家，并继续把尚未绑定的用户评价专家标记为 `blocked`。

自动化映射：

- `tests/unit/test_price_channel_agent_contracts.py`
- `tests/integration/test_price_channel_agent.py`
- `tests/integration/test_competitor_a2a_supervisor.py`
- 可重复真实冒烟：`scripts/smoke_price_channel_live.py`

## AC-04A 统一资料路由

用户通过统一 Source API 提交一次授权资料后，系统必须先运行可解释的确定性规则，并只在
规则不足时通过 Model Gateway 进行受控多标签分类。分类结果只能决定资料应分发给哪些
Agent 和允许审核哪些 Claim 类型，不得自动创建 Evidence、Claim 或研究事实。

同一资料允许多个 route。模型输出必须使用固定枚举，模型单独建议或低置信/冲突结果保持
`needs_review`；自动确认只允许高置信确定性结果或规则与模型一致结果。人工确认、修改和
拒绝必须保存 actor、reason 和时间。未确认、被拒绝、跨项目或已删除资料不得进入要求
route 的领域 Evidence Context。模型失败必须保留审计并回退到规则结果，不得伪造成功。

自动化映射：

- `tests/unit/test_source_routing_contracts.py`
- `tests/unit/test_source_routing_rules.py`
- `tests/integration/test_source_routing_api.py`
- `tests/integration/test_official_product_agent.py`
- 可重复真实冒烟：`scripts/smoke_source_routing_live.py`

## AC-04B 资料范围与准备度

系统必须允许用户确认目标产品、待比较竞品和研究维度，并保存修改人、原因、时间与项目
事件。只有品牌而没有准确型号时，范围不得标记为就绪；同一产品不得同时作为目标产品和
竞品。准备度评估必须由确定性代码根据当前项目的确认 route 和可用 Evidence 实时计算，
不得调用模型或用模型常识补齐缺失资料。

只有状态为 `verified` 或 `partially_verified`、属于已确认 route、显式关联到准确产品，且
Claim 类型符合研究维度的 Evidence 才能满足资料要求。价格 Evidence 还必须匹配 Brief 的
目标地区。只有 eufy 资料、竞品未确认、资料尚未审核、地区错误或处理失败时，接口必须
分别返回 `blocked` 或 `partial` 以及可执行补充动作；不得把 Source Asset 本身当成 Evidence。

自动化映射：

- `tests/unit/test_source_requirement_contracts.py`
- `tests/integration/test_source_requirements_api.py`

## AC-04C 公开来源搜索发现

系统必须把搜索发现保存为项目隔离、可审计的运行记录，并将每个搜索命中明确标记为
`candidate_only`。搜索标题、摘要、相关性分数和 URL 不得直接创建 Source Asset、
Evidence、Claim、Model Call 或业务 Agent Artifact，也不得满足资料准备度；候选只有经过
授权确认、Source Processing、Source Routing、片段审核和 Evidence 晋级后才能供 Agent
使用。

搜索 Provider 必须显式注册，凭据只从本地受控环境读取。未注册、功能关闭、缺少凭据、
认证失败、限流、超时、异常响应和未分类错误必须明确区分并保存失败状态，不得回退到
Mock 结果。候选 URL 必须经过公开地址校验、规范化、去重、域名过滤和数量限制；Provider
响应必须有超时与流式字节上限，任何错误都不得把凭据或原始错误正文写入审计记录。

自动化映射：

- `tests/unit/test_search_discovery_connector.py`
- `tests/integration/test_search_discovery_api.py`

## AC-04D 竞品候选发现与 Candidate Gate

竞品候选发现 Agent 只能消费当前项目中状态为 `succeeded`、intent 为
`competitor_candidate` 的 Search Discovery Run。模型必须引用受控输入中的 candidate ID，
每个输入 ID 必须恰好被提名或排除一次；品牌、型号和变体必须在对应候选文本中明确出现。
目标产品自身、重复产品、编造 ID、遗漏候选或 Schema 无效时不得保存成功 Artifact。

候选 Artifact 必须保持 `candidate_only` 边界，`evidence_ids` 为空，并在人工 Candidate Gate
前不得修改正式竞品范围或满足任何资料要求。确认、拒绝或要求返工必须保存 actor、reason、
时间和事件；只有确认动作选择的准确产品可以原子合并到 Source Requirement Scope。搜索
不足时任务返回 `partial` 或 `blocked`，不得用训练知识或 Mock 凑够竞品数量。

自动化映射：

- `tests/unit/test_competitor_discovery_contracts.py`
- `tests/integration/test_competitor_discovery_agent.py`
- `tests/integration/test_competitor_discovery_api.py`
- 可重复真实冒烟：`scripts/smoke_competitor_discovery_live.py`

## AC-04E 已确认竞品来源接入

系统只能从当前项目已执行 `confirm` 的 Candidate Gate 读取所选 proposal 和 candidate URL，
并在用户再次确认公开资料研究授权后登记 Source Asset。pending、reject、revision、跨项目、
非竞品发现 Artifact 或已经不在正式竞品范围中的陈旧选择必须被拒绝。接入前必须重新执行
公开 URL 安全规范化和域名一致性校验；前端不能在此阶段增加 Gate 未选择的竞品或 URL。

同一 Artifact 的接入必须幂等，批次、Source Asset、queued Collection Job、血缘和事件必须
原子保存。重复 URL 和项目内既有授权链接必须复用；每个接入项保存 Artifact、Decision、
Proposal、Candidate、准确产品和 Source Asset 的结构化关联。接入数据库事务不得访问网页、
调用模型、创建 Source Fragment、Evidence 或 Claim，也不得把 queued 资料表示为研究事实。

事务提交后必须自动把仍为 queued 的任务交给既有网页处理链路，不要求用户再次触发解析。
每个来源必须使用独立处理事务；一个来源失败不得回滚接入批次或阻止其他来源。重复接入不得
重复处理终态任务。批次结束必须重新计算 Source Requirements，并发布包含各终态数量、要求
状态和输入哈希的完成事件。完成解析仍不得自动创建 Evidence 或 Claim。

成功解析的来源必须自动执行既有 Source Routing。高置信度规则可以自动确认；模型辅助后仍
低于阈值的结果必须保持 `needs_review`，不得绕过人工门禁。Source Requirements 必须优先用
Onboarding Item 的准确产品血缘匹配资料；有血缘时禁止回退到标题、URL 或 purpose，把同一
资料错误归属给其他产品。重复接入不得重复分析已有路由。

自动化映射：

- `tests/unit/test_competitor_source_onboarding_contracts.py`
- `tests/integration/test_competitor_source_onboarding_api.py`
- 可重复真实冒烟：`scripts/smoke_competitor_source_onboarding_live.py`

## AC-04F 按产品和维度发现竞品研究资料

系统必须只从当前 Source Requirements Scope 选择具有准确型号的目标产品或已确认竞品，
并按 `official_product`、`price_channel`、`user_review` 生成确定性查询。每个查询必须对应一个
真实 Search Discovery Run；Provider 不可用、失败和无结果必须保持可审计状态，不能用模型
训练知识、Mock URL 或固定业务数据补齐。

搜索命中必须保持 `candidate_only`，发现阶段不得访问网页正文、自动确认授权、调用业务模型，
也不得创建 Source Asset、Source Fragment、Evidence、Claim 或竞品结论。人工 Gate 只能选择
当前批次真实运行中的 candidate ID，确认动作必须显式确认公开资料授权；范围外产品、跨批次
候选、伪造候选和缺少授权必须被拒绝。

确认决定、候选快照、搜索运行、准确产品、产品角色、研究维度和 Source Asset 必须保存不可变
血缘。登记事务必须原子、项目隔离并复用重复 URL；重复相同决定幂等，不同决定冲突。事务提交
后复用现有网页处理、Source Routing 和 Source Requirements 重评链路，单个网页失败不得生成
事实或回滚其他资料。准备度评估必须读取新血缘，不能把一个竞品的资料模糊归给另一个产品。

自动化映射：

- `tests/unit/test_competitor_material_discovery_contracts.py`
- `tests/integration/test_competitor_material_discovery_api.py`
- 可重复真实冒烟：`scripts/smoke_competitor_material_discovery_live.py`

## AC-04G Source Fragment 到 Evidence 的批次门禁

Evidence Draft 只能来自当前项目 ready Source Asset、成功 Collection Job、持久化 Parsed
Artifact 和 verified Source Fragment。创建 Draft 时必须读取 confirmed Source Routing 和结构化
产品/维度血缘，不调用模型、不创建 Evidence，也不允许客户端覆盖原文、Locator、产品、地区
或质量先验。未确认路由、未验证片段、缺失/冲突产品血缘和不允许的 Claim 类型必须明确 blocked。

人工 Gate 只能选择当前批次 eligible item 和后端允许的 Claim 类型。决定必须保存 actor、reason、
选择项和时间；相同决定幂等，不同决定冲突。晋级前必须重新验证 Source Asset、Collection Job、
Parsed Artifact、内容 Hash、Excerpt Hash、Locator 和媒体衍生物 Hash。每项保存 Evidence ID 或
错误码；失败重试不得重复已成功项。相同原文已使用不同证据元数据入湖时不得静默复用。

晋级 Evidence 必须保留 Source Asset、Source Fragment 和 Source Locator，状态初始为
`partially_verified`。质量分数字段只能由版本化确定性策略计算，用于排序而非宣称事实确定性。
批次完成后必须重新计算 Source Requirements；Agent 仍只能通过 Evidence ID 引用这些内容。

自动化映射：

- `tests/unit/test_fragment_evidence_contracts.py`
- `tests/integration/test_fragment_evidence_pipeline_api.py`
- 可重复真实冒烟：`scripts/smoke_fragment_evidence_pipeline_live.py`

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

外部 CLI Runtime 必须通过固定驱动注册，不能接受用户提交的任意可执行命令。每次运行使用项目和 Agent Run 双重隔离的工作目录；密钥只能通过受控环境变量注入，不得写入 Prompt、命令参数、日志、Artifact 或公开 Runtime 目录。CLI 缺失、凭据缺失、探测失败、超时、取消、非零退出、输出过大和结构化输出无效必须明确分类，失败时不得生成研究 Artifact。Runtime 目录只公开经过探测的能力，未验证的网站、图片、音频和视频能力不得宣称可用。

### Source Processing 自动化验收

TXT、Markdown、CSV、JSON 与可提取文本的 PDF 必须生成持久化 `ParsedArtifact` 和带原文定位的 `SourceFragment`；后端必须重新读取隔离工作区中的原始内容并验证每个 excerpt。网页链接、DOCX、图片、音频和视频在没有已注册连接器时必须进入 `blocked`，不得生成片段。失败、重试、排队取消和删除后禁止处理均需保留 Collection Job 状态；外部 Agent 输出不能直接绕过片段验证写入 Evidence。

授权公开网页必须经过 DNS 与每次重定向的公网地址校验、robots.txt、响应类型、解压后大小、超时和重定向次数限制。只允许保存当前项目的 HTML 快照；片段必须携带快照字符范围与 Web Path，并可在第二次读取快照时复核。私网解析、凭据 URL、robots 明确禁止、登录页、二进制响应、过大响应和无效 HTML 必须分类失败或阻塞，不得调用 OpenCode 猜测缺失内容。浏览器隐身、验证码或 Cloudflare 绕过不属于本分支能力。

授权音频和视频必须先在 Collection Job 隔离工作区内完成格式探测、时长/分辨率/流数量限制、标准化音轨提取和有界关键帧抽取。保留供审核的音轨与关键帧必须记录 Hash、媒体类型和时间位置，不能在 API 中暴露本地路径。损坏文件、媒体炸弹、超长内容、无可用音视频流和解码错误必须明确失败，不能交给模型猜测。

语音转写和画面描述必须来自显式注册且声明对应能力的 Media Understanding Connector；未配置 Connector 时任务必须返回 `blocked` 和已经完成的媒体探测结果。模型生成的转写或画面观察只能保存为 `derived` Source Fragment，携带时间范围或帧位置、衍生媒体 Hash、Connector、模型和置信度。`derived` 片段不得直接进入 Evidence Lake；只有项目授权审核人对照保留的音轨或关键帧提交 `verified` 决定后才能晋级，`invalid` 片段必须保持不可用。删除 SourceAsset 必须同时清除所有媒体衍生产物。

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
