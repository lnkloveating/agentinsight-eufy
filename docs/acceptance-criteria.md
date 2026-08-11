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

## AC-26 Security Policy Verification（分支 `workflow/security-policy-verification`）

- 只能消费当前项目已经持久化的 `SecurityPolicyArtifact`，跨项目 Artifact 必须拒绝；
- 验证器不得连接设备控制接口、发送真实通知或把 dry-run 表述为真实部署；
- 每条可合成风险规则必须生成确定性测试场景，每条策略必须覆盖五类 fallback；
- 用户场景只能引用策略声明的 state/signal 和源策略已有 Evidence ID；
- 风险等级、命中规则、干预动作、fallback、断言及 trace 必须结构化返回；
- 场景更新支持时间戳并输出状态 trace；无法可靠合成的缺失或冲突条件必须生成
  `validation_gaps`，不得伪造通过；
- 任一断言失败时进入 `awaiting_policy_revision`；通过或有条件通过才自动进入
  Commercial Evaluation v2；
- Gap 可通过统一 Source Recovery 投影，补研时只针对受影响策略与场景；
- OpenAPI、运行 API、Artifact 历史和 LangGraph 持久化链路保持一致。

验收测试：

- `tests/unit/test_policy_verification.py`
- `tests/integration/test_research_workflow.py`
- `tests/integration/test_runtime_langgraph_integration.py`

## AC-27 Commercial Evaluation v2（分支 `agent/commercial-evaluation-v2`）

- 只能消费当前项目的 User Research、Ecosystem Opportunity、Technical Feasibility 和通过或有条件
  通过的 Policy Verification Artifact；
- 用户价值 Claim 必须引用 User Research Evidence，商业 Claim 必须引用市场、价格、渠道或企业事实；
- 模型不能输出 weighted score、最终 recommendation 或交付结论；后端必须确定性计算；
- 交付运营结论直接消费技术 verdict、策略验证状态、限制和前置条件，不能让商业模型重新猜技术；
- 输出独立的用户价值、商业模式和交付运营结论，以及可验证的商业假设；
- 最终只允许 `recommend_for_validation / conditional / needs_more_evidence / do_not_recommend`；
- `recommend_for_validation` 只允许继续受控验证，不得表示正式上架或保证收益；
- 证据不足必须生成结构化 Commercial Gap；主图进入通用 Source Recovery，恢复后只重跑商业 Agent；
- 达到最大补研次数仍证据不足时返回 `inconclusive`，不得强行给出肯定结论；
- 完成后进入 `awaiting_red_team_review`，包括 `do_not_recommend` 在内的结论都保留给红队审查；
- OpenAPI、FastAPI、Prompt Registry、Model Gateway、Runtime、Artifact 版本和主图契约保持一致。

自动化映射：

- `tests/unit/test_commercial_evaluation_v2.py`
- `tests/integration/test_research_workflow.py`
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

## AC-03E 竞品用户评价专家

用户评价专家只能读取当前项目中状态为 `verified` 或 `partially_verified`、来源资料已确认
路由到 `user_review`、明确绑定到主管请求产品，且 Claim 类型为 `user_opinion` 的 Evidence。
模型不得联网、搜索或使用训练知识，不得把厂商描述、商品规格、搜索摘要或没有用户表达的
页面文字改写成用户观点。

每个评价主题必须绑定准确产品、情感方向、用户表达、事件场景、影响和 Evidence IDs。后端
根据引用 Evidence 数量及独立来源数量确定主题是单一报告还是重复主题，模型不得自行声称
“大量用户”“普遍存在”或统计百分比。单条评论可以保存为观察，但不能满足重复主题门禁。
正反意见必须分别保留；资料没有代表性、地区/用户分群未知、来源单一或样本过少时，必须
形成样本限制或补研问题。

确定性 Validator 必须拒绝越界 Evidence、错产品、非 `user_opinion`、重复主题 ID、主题引用
产品血缘不一致和无引用事实。没有合格证据时返回 `blocked`；产品范围、独立来源或重复主题
覆盖不足，或存在高严重度缺口时返回 `partial`；只有每个请求产品均有受支持的重复主题、
达到独立来源门槛且无高严重度缺口时，才允许 `completed`。父级竞品主管必须真实绑定三个
专家，不能再以 `specialist_not_bound` 代替用户评价结果。

自动化映射：

- `tests/unit/test_competitor_user_review_contracts.py`
- `tests/integration/test_competitor_user_review_agent.py`
- `tests/integration/test_competitor_a2a_supervisor.py`
- 可重复真实冒烟：`scripts/smoke_competitor_user_review_live.py`

## AC-03F 竞品综合与证据审计

三个竞品专家均产生带 Evidence ID 的发现后，主管才允许调用竞品综合模型。综合结果必须包含
逐产品优点、缺点与权衡、跨产品差异和待 Ecosystem Opportunity Agent 验证的机会假设；机会假设
不得作为已验证未来产品结论。后端必须确定性检查每个引用是否来自本轮专家输出、是否仍存在于
父级 Evidence Context、产品归属是否一致，以及单维度判断是否越过专家边界。任何越界引用都
必须使本轮 Artifact 失败。缺少任一专家发现时不得调用综合模型，并返回
`blocked_by_specialist_coverage`；覆盖不足时只能输出 `partial`，且研究缺口保持可见。

验收映射：

- `tests/unit/test_competitor_synthesis_contracts.py`
- `tests/unit/test_competitor_synthesis_validation.py`
- `tests/integration/test_competitor_synthesis_agent.py`
- 可重复真实冒烟：`scripts/smoke_competitor_synthesis_live.py`

## AC-03G 竞品主路径桥接

LangGraph 必须在用户研究和竞品研究两个并行节点均返回后生成强类型 `ResearchHandoff`，
并把两个 Artifact、合并后的 Evidence IDs、竞品产品范围、机会假设 ID、缺失研究维度和补研
问题写入 `ResearchState`。Ecosystem Opportunity Agent 只能读取这份交接和策略允许的上游
Artifact，不能从 Runtime 存储中自行猜测最新结果。

状态为 `completed` 的结果可以正常交接；状态为 `partial` 的竞品综合只有在结构有效、三个
专家输出完整、Evidence Audit 为 `passed_with_gaps` 且所有 Payload 引用均属于父级 Artifact
时，才允许以 `ready_with_gaps` 进入生态机会阶段。Foundation 占位结构、缺失 Evidence、
越界引用、审计失败或产品覆盖范围不一致必须阻断。阻断时只重跑受影响的用户研究或竞品研究
任务；Checkpoint 恢复不得重复执行已经成功且未受影响的并行节点。

验收映射：

- `tests/unit/test_competitor_mainpath_bridge.py`
- `tests/unit/test_workflow_contracts.py`
- `tests/integration/test_research_workflow.py`

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

## AC-04H 资料失败后的用户补充与定向恢复

网页或媒体资料处理失败，或虽然处理成功但没有形成满足当前 Source Requirements 的有效
Evidence 时，后端必须基于真实 Collection Job、资料血缘和准备度评估生成恢复任务。恢复任务
必须说明失败原因、涉及产品、缺少的具体字段及受影响 Agent；不得要求用户只能盲目更换链接，
也不得调用模型猜测网页或媒体中未取得的内容。
竞品缺口优先读取 Source Requirements；尚未被该领域模型覆盖的缺口只能接受受信任工作流主管
传入的具体问题和已知 Agent 类型，不能由恢复服务或前端临时生成事实性问题。

用户补充必须确认授权和准确性，并保存为独立的 `user_input` Source Asset、成功 Collection Job、
可定位 Source Fragment、人工确认 Source Routing 和 `partially_verified` 的
`user_declaration` Evidence。记录必须同时关联原失败资料、恢复任务、提交批次、替代 Source
Asset 和 Evidence IDs。它不能被标记成官网或第三方来源，重复 request ID 必须幂等。

提交后必须重新计算 Source Requirements。受影响要求满足时返回 `targeted_retry`；仍不足时保持
`needs_more_information`。用户可以明确选择 `proceed_with_gaps`，但该决定不得创建 Evidence，
未知项必须继续可见。恢复指令只映射当前 Task Plan 中受影响的 Agent/任务，不能要求已经成功且
未受影响的节点重跑。

自动化映射：

- `tests/unit/test_source_recovery_workflow.py`
- `tests/integration/test_source_recovery_api.py`

## AC-04I 项目级共享 Evidence 检索

用户研究、竞品官方产品、竞品价格渠道、竞品用户评价和产品技术 Agent 必须通过同一共享检索
服务构建 `AgentEvidenceContext`。检索只能返回当前项目中状态为 `verified` 或
`partially_verified` 的 Evidence；其他项目、未审核、过期、Mock 或无效记录不得进入 Context。

共享服务必须支持 Claim、来源、Source Asset、产品、地区、用户分群和精确 Evidence ID 过滤，
并统一执行字符预算、来源多样性和稳定 Context Hash。带问题的检索使用可解释的确定性词法
相关度；产品技术等上游边界不得扩大的阶段必须保留明确 Evidence ID 顺序。空 Source Route
不得退化成读取项目全部 Evidence。相关度只用于检索排序，不能替代 Evidence 状态或 Claim Gate。

第一版不得声称具有向量语义检索能力，也不得调用生成模型补写检索结果。公共检索接口必须
返回策略、查询 Hash、候选数、精确 Evidence ID、命中词和匹配原因，便于前端解释 Agent 使用
了哪些资料。

自动化映射：

- `tests/unit/test_evidence_retrieval_contracts.py`
- `tests/integration/test_evidence_retrieval.py`
- 用户研究、三个竞品专家和产品技术 Agent 的既有集成测试

## AC-04J 通用 Agent 缺口与资料恢复

用户研究、竞品研究、产品技术以及后续商业与红队 Agent 的持久化 Artifact 缺口必须能够投影为
统一 `AgentArtifactGap`。没有原生 ID 的缺口须按语义生成跨 Artifact 版本稳定的 `gap_id`；路径
Agent 类型必须与 Artifact 类型一致，前端不得自行伪造缺口或受影响任务。

任一 Gap 都应能创建统一 Source Recovery，返回结构化字段、证据类型提示、受影响候选、Agent
和 Task。直接填写沿用可追溯 `user_declaration`；文件、PDF、网页和 API 资料必须先通过既有
Source Processing、Routing 与 Evidence Gate，再把同项目、同 Source Asset 的 eligible Evidence
绑定到指定字段。原文件、未审核 Fragment、Mock、Invalid 或跨项目 Evidence 不得解除缺口。

补研解决后只返回 `targeted_retry` 范围，不直接重跑整张图；尚未满足时保持等待，用户可明确
带缺口继续。旧产品技术补研接口必须继续兼容，并使用同一个通用实现。

自动化映射：

- `tests/unit/test_agent_gap_projector.py`
- `tests/integration/test_universal_agent_source_recovery_api.py`
- `tests/unit/test_legacy_single_product_cleanup.py`

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

## AC-07 生态机会比较

在证据允许时，系统动态生成设备功能、设备产品或生态服务机会，并比较用户安全目标、跨设备协作、
持续状态理解、主动补证、隐私边界、离线降级和验证可行性。模型输出目标为 3 个、上限为 5 个，
但证据不足时允许为 0，必须显示真实 `portfolio_gaps`，不能用 Mock 或固定门铃场景补齐。

`agent/ecosystem-opportunity` 的验收映射：

- 每个候选必须引用用户研究和竞品生态 Evidence，具体设备能力只能来自 Device Capability Graph；
- 后端审计 Evidence、竞品机会信号、设备角色、跨设备信息流、AI Removal Test 和稳定 Gap ID；
- 补研统一调用领域 Agent 通用 Source Recovery API，不存在单产品专用恢复接口；
- 用户补充内容保存为 `user_declaration` Evidence，并保留 Artifact、Gap、Submission 与 Evidence 血缘；
- 已解决 Evidence 只恢复 Ecosystem Opportunity，不无差别重跑用户研究或竞品研究；
- 重复候选、虚构 Evidence、虚构竞品信号或把未知设备能力写成事实时确定性失败。

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

## AC-16 生态机会契约（分支 `domain/ecosystem-opportunity-contract`）

这是 eufy 家庭安防生态方向的第一个基础分支，只定义"生态级解决方案机会"的公共契约和领域模型，
不实现真实 Agent、不调用大模型、不生成研究结果，也不落地设备能力图、AI Native Gate 或商业评估。

验收要求：

- 系统可以在类型层明确区分设备功能（`device_feature`）、设备产品（`device_product`）和生态服务
  （`ecosystem_service`）；
- 生态候选可以表达用户安全目标、目标用户与问题、`EcosystemBlueprint`（设备角色、跨设备信息流、
  部署位置、隐私/权限边界、离线与降级行为、已知盲区）和 `AINativeCase`（含 AI 移除测试）；
- 蓝图只描述"方案要求什么角色和能力"，不得未经 Evidence 断言某个真实 eufy 型号一定具备该能力；
- 模型可输出结构（`*ModelCandidate` / `*ModelOutput`）不允许包含 `gate_status`、`gate_issues` 或任何
  确定性判定，由 `extra="forbid"` 在结构层强制；`gate_status` 与稳定 `gap_id` 属于后端；
- 确定性校验覆盖：未知 `scope_level`、重复 `opportunity_id` / `role_id` / `flow_id` / Evidence ID /
  `competitor_gap_ids` / `summary_evidence_ids` / `affected_opportunity_ids`、信息流引用不存在的角色、
  `generated_candidate_count` 超过 5、未知字段，以及 OpenAPI 字符串长度边界；
- 设备角色和 AI 移除测试中的嵌套 Evidence ID 必须属于候选顶层 `evidence_ids`，并进入统一引用审计集合；
- `schema_name`、`schema_version`、`artifact_type`、可发布状态和 Artifact Evidence 唯一性必须与
  OpenAPI 保持一致，内部不得生成公共 API 无法表达的 Artifact；
- Coverage 的生成数、晋级数和生态服务数必须分别等于真实候选、`passed` 候选和
  `ecosystem_service` 候选数量；Gap 不得引用当前组合中不存在的 Opportunity；
- Evidence 不足时允许零个或少于三个候选，但必须包含 `portfolio_gaps`，不得用固定模板凑数；
- `EcosystemOpportunityArtifact` 与通用 `ResearchArtifact` 双向转换，并在缺失 `gap_id` 时确定性回填；
- `ECOSYSTEM_OPPORTUNITY` 是新项目唯一的机会生成类型，主路径以 `PLANNED_AGENT_TYPES` 为准；
- 本分支不声称已经生成任何生态方案。

自动化映射：

- `tests/unit/test_ecosystem_opportunity_contracts.py`
- `tests/unit/test_workflow_contracts.py`（主路径角色集合改以 `PLANNED_AGENT_TYPES` 为准）
- `tests/integration/test_research_workflow.py`、`tests/integration/test_runtime_langgraph_integration.py`
  （主图执行集合为 `RESEARCH_MANAGER` 加 `PLANNED_AGENT_TYPES`，新增枚举暂不接入）

## AC-17 设备能力图（分支 `evidence/device-capability-graph`）

设备能力图为生态机会与后续安全策略提供确定性事实边界，不负责生成策略，也不调用大模型猜测设备能力。

验收要求：

- 厂商通用设备目录与用户家庭设备实例分开保存，所有数据按研究项目隔离；
- 厂商设备身份和能力断言只接受当前项目 `verified` 或 `partially_verified` Evidence，拒绝
  `mock`、`invalid`、`unverified`、`outdated` Evidence 以及其他项目 Evidence；
- 能力可以表达 Sensor、Action、Compute、Storage、Connectivity 和 Context，并记录可用性、最大延迟、
  数据处理位置、授权要求、离线支持、fallback 与置信度；
- 同一设备能力同时存在支持与不支持的合格 Evidence 时必须保留两者，并在能力查询中返回 `conflict`，
  不得以后写入的数据静默覆盖先前事实；
- 用户授权保存家庭设备快照时只收集粗粒度位置、设备角色、在线状态和授权状态，不接收精确地址、序列号、
  原始家庭视频或生物识别数据；每次修改生成新版本，旧版本标记为 `superseded`；
- 未映射目录的家庭设备或未找到对应能力时返回 `unknown`；设备离线、未授权或能力明确不可用时返回
  `unavailable`；满足能力、证据和运行状态时才返回 `available`；
- 查询结果返回准确的 Capability Claim ID 和 Evidence ID，供生态机会、技术可行性和前端证据下钻复用；
- 查询时重新检查 Evidence 当前状态；已经 outdated/invalid/移除的历史 Evidence 不得继续生成 `available` 结论；
- 删除仍被任何家庭快照引用的目录设备时返回冲突，不级联删除用户快照；
- 企业 eufy Device API 未配置时不创建假 Adapter、不声明已联调成功，后续可以在不改变公共查询契约的前提下接入；
- 新增 OpenAPI、数据库迁移、领域/服务单元测试和 HTTP 集成测试。

自动化映射：

- `tests/unit/test_device_capability_contracts.py`
- `tests/unit/test_device_capability_query.py`
- `tests/integration/test_device_capability_api.py`
- `tests/integration/test_device_capability_migration.py`

## AC-18 AI 原生家庭安防研究范围（分支 `domain/ai-native-home-safety-research-scope`）

本分支只允许新项目以家庭安防生态、安全目标、授权信号、隐私/干预边界和验证期望描述研究范围，
不再接受旧单品式 Research Brief。

验收要求：

- `ResearchBrief` 的 `research_scope` 只能是 `home_safety_ecosystem`；
- 目标生态、目标用户、市场、安全领域、安全目标和风险场景不能为空，目标生态与对照生态不得重叠；
- `category`、`target_user`、`region`、`scenarios`、`constraints`、`focus_dimensions` 作为额外字段被 422 拒绝；
- 明确公开资料、用户上传、企业内部资料和家庭事件四类授权边界；
- 明确原始媒体、限制区域、保留策略和外部共享边界；
- 高影响动作必须要求人工批准，禁止通过请求关闭该约束；
- 用户研究、竞品主管、资料发现、片段 Evidence 和资料要求服务只读取新 Brief 字段；
- 地区型证据使用 `markets[0]`，不得因为旧 `region` 缺失而永久停留在 `partial`；
- 老人安全、包裹保护等是动态场景，不是后端固定候选；
- 历史迁移和旧 Artifact 读取不等于支持旧 Brief，新项目不得静默迁移旧字段。

自动化映射：

- `tests/unit/test_home_safety_research_scope.py`
- `tests/research_brief.py`
- `tests/integration/test_project_lifecycle.py`
- `tests/integration/test_source_requirements_api.py`
- 所有创建项目或直接构造 `ResearchBrief` 的后端测试。

## AC-19 Research Brief 多轮追问（分支 `agent/research-brief-clarifier-v2`）

模糊研究目标必须先进入项目外的持久化追问会话。模型可以提取用户明确回答并生成动态问题，
但只有确定性代码确认正式 `ResearchBrief` 全部字段合法后才能进入确认状态。

验收要求：

- `POST /research-brief-clarifications` 使用默认或用户选择的真实 Model Gateway 模型，不返回固定假问题；
- 会话、对话、部分草稿、问题、版本和模型用量可持久化读取；
- 模型生成的每个草稿叶子字段必须引用现有用户消息 ID，无引用字段不得写入草稿；
- 未明确回答时，原始媒体、家庭事件、外部分享、第三方通知和其他权限字段保持缺失；
- 问题只针对后端仍缺失的字段，每轮最多六个；模型问题无效时由后端生成明确补充提示，不补造答案；
- `ready_for_confirmation` 必须同时满足零缺失字段和完整 `ResearchBrief` Schema 校验；
- 追问完成后仍由用户确认，再调用现有项目创建 API，不自动绕过 Brief Gate；
- 过期 `expected_version` 返回 409，模型失败保存安全错误分类；
- 模型调用审计允许关联追问会话，不要求伪造 Project 或 Agent Run；
- 数据库迁移可从 `0019` 升级到 head，并可降级回 `0019`。

自动化映射：

- `tests/integration/test_brief_clarification_api.py`
- `tests/integration/test_brief_clarification_migration.py`
- `tests/integration/test_model_gateway.py`

## AC-20 竞品生态分析（分支 `agent/competitor-ecosystem-analysis`）

竞品研究必须保留“具体产品事实”和“生态层判断”两层，不能让模型直接凭常识描述 Ring、Google Nest、Arlo 或 eufy 生态。

验收要求：

- 生态范围只来自已确认 Research Brief 的 `target_ecosystems` 与 `comparison_ecosystems`；候选产品只来自已有 Competitor Discovery、资料接入和 Evidence 血缘；
- 官方产品、价格渠道和用户评价三个 A2A 专家继续并行提取具体产品事实，旧产品事实综合作为生态综合的内部上游，不再充当新项目最终竞品 Artifact；
- 生态综合固定覆盖安全目标、跨设备协作、跨时间状态、主动感知、不确定性、分级干预、本地/云分工、隐私授权、离线降级、照护者流程、失败修订和商业模式 12 个维度；
- `supported`、`limited`、`contradicted` 必须引用当前项目、对应产品且属于声明专家维度的 Evidence ID；
- 没有合格 Evidence 的维度只能是 `unknown`，不得引用 Evidence，也不得改写为“竞品没有该能力”；
- 同一具体产品不得映射到多个生态；生态比较与机会信号只能引用参与生态已映射产品的 Evidence；
- 后端确定性生成覆盖矩阵、资料缺口、审计状态和质量分，模型不得自行决定完成状态；
- 资料不全但审计通过时返回 `partial` 与 `passed_with_gaps`，三个事实专家无法形成有效上游时返回显式 `blocked`，不得生成伪成功结论；
- v2 `competitor_ecosystem_analysis` Artifact 可以进入 `ResearchHandoff`，并投影生态范围、产品范围、12 维状态、机会信号和补研问题；历史 v1 Artifact 仍可读取；
- `POST /projects/{project_id}/agents/competitor-ecosystem` 与 Artifact 历史查询接口和 OpenAPI 一致，运行记录、模型调用与 Artifact 版本可审计；
- 本分支不生成未来生态方案，不判断技术或商业上架结论；这些属于后续 Ecosystem Opportunity、Technical Feasibility 与 Commercial Agent。

自动化映射：

- `tests/unit/test_competitor_ecosystem_analysis.py`
- `tests/unit/test_competitor_mainpath_bridge.py`
- `tests/integration/test_competitor_synthesis_agent.py`

## AC-21 生态机会 Agent（分支 `agent/ecosystem-opportunity`）

用户研究、竞品生态、共享 Evidence 和设备能力图必须通过真实 Model Gateway 与确定性门禁生成
版本化生态机会，而不是复用固定场景模板。

验收要求：

- `POST /projects/{project_id}/agents/ecosystem-opportunity` 和 Artifact 历史接口与 OpenAPI 一致；
- 只消费最新 advancing User Research 与 Competitor Ecosystem Artifact；上游未就绪时不调用模型，
  返回显式 blocked Artifact 和补研问题；
- Context Builder 只投影设备身份与能力断言均有当前合格 Evidence 的 Capability Graph 事实；
- 所有模型引用属于 Research Handoff、补研 Evidence 或当前 Capability Graph，编造 Evidence ID 被拒绝；
- 每个候选同时引用用户和竞品 Evidence，竞品机会 ID 必须真实存在；
- 已证实设备能力引用 Capability Graph Evidence；未知能力显式保留为 technical hypothesis 并生成
  `portfolio_gap`，不支持、不可用或冲突能力不得伪装成可用；
- `ecosystem_service` 至少包含两个设备角色和跨设备信息流；候选名称、安全目标和 ID 不重复；
- 动态生成目标 3 个、最多 5 个；不足时保留真实数量和稳定 Gap，不使用老人、门铃、包裹或
  Guardian 固定模板凑数；
- Runtime 保存 Agent Run、模型调用、输入 Artifact 血缘和输出 Artifact 版本，密钥不进入 Prompt；
- 本分支不接入 LangGraph 主图，不宣称通过 AI Native、技术、商业、红队或上架 Gate。

自动化映射：

- `tests/unit/test_ecosystem_opportunity_agent.py`
- `tests/unit/test_ecosystem_opportunity_contracts.py`
- `tests/integration/test_ecosystem_opportunity_agent.py`

## AC-22 AI Native Ecosystem Gate（分支 `workflow/ai-native-ecosystem-gate`）

生态机会必须经过独立确定性检查和 Human Gate，普通检测通知、单设备固定规则或移除 AI 后核心价值仍
成立的候选不能冒充 AI 原生家庭安防生态。

验收要求：

- 主图从 Evidence Readiness 进入 Ecosystem Opportunity，再进入 AI Native Gate；Product Technical v1、
  旧 Commercial 和旧 Red Team 不再属于当前新项目任务计划；
- Gate 不调用模型、不生成候选、不修改原 Artifact，只消费版本化 `EcosystemOpportunityArtifact`；
- `ecosystem_service` 必须至少有两个必需设备角色进入跨设备信息流；
- AI removal test 必须说明移除 AI 后核心价值不能成立，并列出丢失能力；
- 模型职责与权限、动作和安全等确定性职责必须分离；
- 候选必须包含失败修订闭环、隐私边界、离线/fallback、Human Review Point，以及 failure 和 adversarial
  部署前验证；
- 上游 Evidence/Capability Gate 已阻止的候选不能晋级；失败候选生成稳定 Revision Request；
- 通过确定性检查后仍暂停 Human Gate，由人确认开放目标、持续状态、主动补证与失败修订语义；
- 批准必须选择至少一个确定性合格 Opportunity，后端拒绝被阻止、未知或重复 ID；
- `revise` 只重跑 Ecosystem Opportunity；达到最大迭代后返回 inconclusive；
- 只有 Artifact 存在真实 `portfolio_gaps` 时才允许 `research_more`；统一 Source Recovery 完成后只恢复
  Ecosystem Opportunity，不重复用户与竞品研究；
- Checkpoint 能在 Ecosystem Opportunity 节点失败后恢复该节点，不重复已完成并行研究；
- 批准后只能把确定性合格且由用户选择的 Opportunity 交给技术可行性 Agent，不得调用旧单产品链路；
- 本分支不新增公共 HTTP API，详细状态与前端语义见 `docs/ai-native-ecosystem-gate.md`。

自动化映射：

- `tests/unit/test_ai_native_ecosystem_gate.py`
- `tests/unit/test_workflow_contracts.py`
- `tests/integration/test_research_workflow.py`
- `tests/integration/test_runtime_langgraph_integration.py`

## AC-23 移除旧单产品机会链路（分支 `cleanup/remove-legacy-single-product-path`）

新项目不得再通过 Product Technical v1 生成或恢复单产品候选。验收要求：

- OpenAPI 和 FastAPI 均不再暴露旧单产品运行、Artifact 查询或专属 Source Recovery 路径；
- 旧 Adapter、Prompt、Service、Context Builder、配置和专属测试全部删除，应用启动时不再注册旧 Runtime；
- `ResearchAgentType`、`RecoverableAgentType` 和上下文策略只把生态机会作为当前机会生成类型；
- 技术资料和市场研究资料不再路由到已删除的 Agent，而是进入生态机会或后续商业评估；
- `ResearchHandoff` 对外只序列化 `ready_for_ecosystem_opportunity`；旧 Checkpoint 中的
  `ready_for_product_technical` 只允许作为读取别名，不能重新出现在新状态中；
- 通用 Evidence、Source Recovery、Event Understanding 领域结构、设备能力图和生态机会链路保持可用。

自动化映射：

- `tests/unit/test_legacy_single_product_cleanup.py`
- `tests/unit/test_workflow_contracts.py`
- `tests/unit/test_agent_gap_projector.py`
- 全量 Ruff、Mypy 与 Pytest。

## AC-24 技术可行性 Agent（分支 `agent/technical-feasibility`）

Human Gate 选中的生态机会必须经过 Evidence 与 Device Capability Graph 约束的技术评估，模型不能
自行宣布可落地。

验收要求：

- OpenAPI 与 FastAPI 提供运行和 Artifact 历史接口，请求必须选择 1–5 个唯一 Opportunity ID；
- 只消费最新 Ecosystem Opportunity、Research Handoff、共享 Evidence、设备能力图和已解决补研证据；
- 模型输出只包含技术需求、架构、Demo 边界、失败模式和补研问题，不包含最终 verdict；
- data/interface、deployment、performance、privacy、resilience 必须全部覆盖；
- 非 unknown 技术状态必须引用当前受控 Evidence，编造或越界 Evidence ID 被拒绝；
- 设备必需能力由后端与 Capability Graph 精确匹配，`unknown` 不得改写为 unsupported；
- 后端确定性生成 `demo_feasible / conditionally_feasible / insufficient_evidence / not_feasible`；
- 缺证据时生成稳定 Gap，主图进入通用 Source Recovery，补证后只重跑技术 Agent；
- 至少一个可验证机会才进入 `awaiting_security_policy`；全部明确不可行或补研预算耗尽时返回 inconclusive；
- Runtime 保存 Agent Run、模型审计、Artifact 版本和上游血缘，不保存 Key 或家庭原始媒体。

自动化映射：

- `tests/unit/test_technical_feasibility_agent.py`

## AC-25 Security Policy Compiler（分支 `agent/security-policy-compiler`）

- 只编译用户选择且技术 verdict 为 `demo_feasible` 或 `conditionally_feasible` 的生态机会；
- 模型只能生成策略意图，不能生成后端拥有的执行模式、ID、版本、fallback、invariant 或 Hash；
- Brief 未授权的信号、生态蓝图不存在的设备角色、未允许的干预和越界 Evidence ID 必须失败；
- 输出固定为 `dry_run`，且包含信号不可用、设备离线、网络离线、不确定状态和权限拒绝五类降级；
- 高影响动作必须显式要求人工批准，任何策略均不得直接控制真实家庭设备；
- 同一语义策略保留稳定 Hash，新 Artifact 提升版本并输出新增、删除、改变或未改变差异；
- LangGraph 在技术验证后执行 Compiler，成功后进入 `awaiting_policy_verification`；
- HTTP API 与 `docs/api/openapi.yaml` 一致，Artifact 可按版本查询并通过 Evidence ID 下钻。

验收测试：

- `tests/unit/test_security_policy_compiler.py`
- `tests/integration/test_research_workflow.py`
- `tests/integration/test_runtime_langgraph_integration.py`
- `tests/unit/test_workflow_contracts.py`
- `tests/integration/test_research_workflow.py`
- `tests/integration/test_runtime_langgraph_integration.py`

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
