# Shared Evidence Retrieval Foundation

## 目标

所有领域 Agent 共享同一套项目级 Evidence 检索边界，不再各自复制查询、截断、来源去重和
Context Hash 逻辑。Evidence Lake 仍是事实来源；检索服务只决定哪些已审核 Evidence 可以进入
本次 Agent Context，不创建事实、不调用生成模型，也不把搜索摘要或未审核 Fragment 当成知识。

```text
Source Asset
→ 确定性解析与 Source Fragment
→ 路由确认与 Evidence 晋级
→ Evidence Lake
→ Evidence Retrieval Service
→ AgentEvidenceContext
→ 用户研究 / 竞品专家 / 产品技术 / 后续商业与红队 Agent
```

## 第一版检索策略

第一版不依赖 Embedding API 或向量数据库，提供三种确定性策略：

- `metadata_quality`：按项目、状态、Claim、来源、产品、地区和用户分群过滤，再按证据质量与
  来源多样性选取；
- `lexical_metadata`：在元数据过滤后，对问题和标题、产品、地区、用户分群、原文片段做中英文
  词法相关度排序；中文连续文本同时生成双字词项；
- `exact_evidence_ids`：严格保留上游 Artifact 交接的 Evidence ID 顺序，适用于产品技术等不可
  扩大引用边界的阶段。

所有策略都只接受 `verified` 和 `partially_verified` Evidence，并执行项目隔离、单条片段字符
上限、总字符预算和稳定 Context Hash。`partially_verified` 不会被伪装为已验证事实，最终 Claim
仍须通过既有 Evidence ID 门禁。

## 公共契约

```http
POST /api/v1/projects/{project_id}/evidence/retrievals
```

请求可包含：

- `consumer` 和可选研究问题；
- Claim、来源类型、Source Asset、精确 Evidence ID；
- 产品、地区、用户分群；
- 最大 Evidence 数、单条和总字符预算；
- 是否要求词法命中、来源多样性或严格保留 Evidence 顺序。

响应返回：

- `AgentEvidenceContext` 与 Context Hash；
- 元数据候选数、实际纳入数和省略数；
- 每条 Evidence 的稳定排名、相关度、命中词和匹配原因；
- 查询契约 Hash，不持久化原始模型 Prompt 或生成内容。

## 现有 Agent 迁移

- 用户研究：共享状态门禁、质量排序、来源多样性和字符预算；
- 竞品官方产品：额外限制已确认 `official_product` Source Route 和官方事实 Claim；
- 竞品价格渠道：额外限制 `price_channel` Route、价格渠道 Claim 和精确地区；
- 竞品用户评价：额外限制 `user_review` Route 和 `user_opinion`；
- 产品技术：只读取 `ResearchHandoff` 合并及已解决补研 Evidence ID，并保留交接顺序。

后续商业和红队 Agent 直接复用同一服务，不建立互相冲突的独立知识副本。

## 安全边界

- 不跨项目检索；未来企业级共享资料必须另行建立显式授权范围；
- 不检索 `unverified`、`outdated`、`mock` 或 `invalid` Evidence；
- 空的已确认 Source Route 返回空 Context，不能退化成读取整个项目；
- 词法命中只是检索相关度，不代表事实正确或 Claim 已被支持；
- 向量 Provider 留待后续混合检索分支，不能静默假装已经具备语义向量能力。

## 与资料恢复的关系

RAG 只能从已有资料中找证据，不能解决资料根本不存在的问题。任一 Agent 发现关键缺口时，仍
应创建 Source Recovery；用户上传文件、网页或直接填写后，内容经过现有解析、审核和 Evidence
晋级，再自动成为共享检索的候选。统一 Agent Gap 与全局补研弹窗不属于本基础分支。
