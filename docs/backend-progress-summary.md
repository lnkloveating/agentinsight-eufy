# 后端进度与前端适配说明

> 更新时间：2026-08-09
>
> 基线分支：`main`
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

> 项目生命周期、统一资料接入与多标签路由、资料范围和准备度检查、公开来源搜索发现、授权公开网页快照、确定性资料解析、证据和候选场景数据底座、LangGraph 编排底座、Agent Runtime Core、多模型 Model Gateway、安全的 OpenCode CLI Runtime、用户研究 Agent、竞品 A2A 运行底座与官方产品专家已经完成；竞品候选判断与审批、价格渠道、用户评价、竞品综合及其余领域 Agent 尚未接线，因此系统还不能自动完成一整轮真实行业调研。

### 2.1 已完成并合并到 `main`

| 模块 | 当前能力 | 对前端的意义 |
|---|---|---|
| 项目生命周期 | 创建/查询项目、Brief 人工审批、状态迁移、持久化事件 | 可以实现项目列表、Brief 确认页和审批面板 |
| SSE 事件 | 历史事件回放、实时事件、断线续传游标、心跳 | 可以实现实时研究时间线和连接状态 |
| Evidence Foundation | Evidence、Collection Job、Claim、去重、跨项目隔离、Claim Gate、失败记录 | 可以实现 Evidence Center 和 Claim-Evidence 关系展示 |
| Source Ingestion | 用户/企业授权文件上传、公开链接登记、项目隔离存储、哈希去重、授权审计、删除与 Collection Job | 可以实现真实资料输入页和资料资产列表 |
| Source Processing | 文档/网页确定性解析；音视频容器探测、标准化音轨、关键帧、衍生产物 Hash；失败/重试/取消、媒体人工复核与受控 Evidence 入湖 | 可以展示网页和媒体处理状态、可回溯片段、保留音轨/帧及审核操作；未配置 ASR/视觉 Connector 时媒体语义阶段明确 blocked |
| Source Routing | 可解释规则、必要时模型辅助、多标签 route、置信度、人工确认/拒绝、模型审计、项目事件 | 可以提供统一资料中心的“自动识别”，用户不再为每个 Agent 重复上传或必须理解 claim_type |
| Source Requirements | 保存目标产品、竞品和研究维度；按确认 route、准确产品、地区和 Evidence 实时计算 `ready/partial/blocked`；返回补充动作 | 可以实现资料准备清单，区分“已检测资料”和“已满足 Evidence”，阻止只有 eufy 资料时误跑完整竞品分析 |
| Search Discovery | 通过显式注册的 Tavily Search Provider 发现公开候选 URL；项目隔离运行、失败分类、安全去重和域名过滤；结果固定为 `candidate_only` | 可以实现“查找资料”动作和候选来源列表；不能把搜索摘要显示成证据或自动勾选为已满足 |
| Innovation Foundation | 事件理解结构、八维评分、红队结果、候选组合门禁、持久化查询 | 可以实现候选机会比较页，不应继续只依赖旧 `Concept` 类型 |
| LangGraph Foundation | 研究共享状态、并行研究节点、Checkpoint、三个 Human Gate、定向重跑 | 可以按目标流程设计节点图和 Gate UI，但当前 HTTP 流程不会自动跑完整真实 Agent |
| Agent Runtime Core | Agent Run、Adapter Registry、Artifact Store、超时、取消、错误分类、运行隔离、运行事件 | 可以展示 Agent 状态、错误、Artifact 元数据和运行历史 |
| External CLI Runtime | 固定 Driver 注册、CLI 健康探测、项目/运行隔离目录、输出限制、超时/取消、密钥脱敏、OpenCode Driver | 可以通过 `/runtimes` 展示外部 Agent 是否真实可用；不能把未声明的网站/视频能力标成可用 |
| Model Gateway | 模型目录、项目默认模型、Agent 级覆盖、Prompt 版本、结构化输出、重试、Token/成本审计 | 可以实现模型选择器和 Agent 调用审计展示 |
| 主办方模型路由 | 已接入 GLM 5.2 与 DeepSeek V4 Pro，并完成真实联网冒烟测试 | 前端只使用 `/models` 返回的 `model_id`，不接触 API Key |
| 用户研究 Agent | 消费受控 Evidence Context，输出带 Evidence IDs 的事件链、痛点和未满足需求 | 可以启动真实用户研究并展示证据覆盖、未知项和模型审计 |
| 竞品 A2A Foundation | 竞品主管、三类 EvidenceRequest、并行专家网关、A2A Task 审计、超时和定向恢复 | 可以按 SSE 事件展示三条专家泳道；尚未实现的专家会明确 blocked |
| 竞品官方产品专家 | 从受控官方 Evidence 中提取产品身份、能力、规格、兼容性、限制和未知项；确定性校验范围与引用 | 可以展示官方专家的真实结构化结果和证据覆盖；不能把父级 partial 当成完整竞品结论 |

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

当前仍缺少：

- HTTP 项目生命周期与 LangGraph 完整启动/恢复的生产接线；
- 价格渠道、用户评价、产品技术、商业和红队等业务 Prompt；
- 自动竞品候选判断、候选审批 Gate 和确认后的批量 Source Onboarding；
- 把已验证 SourceFragment 提供给领域 Agent 和外部 Runtime 的语义分析接线；
- 真实 ASR 和视觉模型 Connector（当前主办方两个文本模型不能替代）；
- 竞品能力矩阵与差异化综合；
- 最终报告、Package Risk Demo 和飞书集成。

生产环境没有注册业务 Prompt 或真实业务 Adapter 时会明确失败，不会用 Mock 结果冒充调研完成。

## 3. 当前真实可用的 `/api/v1` 接口

| 方法 | 路径 | 状态 | 前端用途 |
|---|---|---|---|
| `GET` | `/health` | 可用 | 服务健康状态 |
| `GET` | `/models` | 可用 | 模型选择器；返回安全模型目录和凭据可用状态 |
| `GET` | `/runtimes` | 可用 | 外部 Agent 选择器；返回 CLI、凭据、版本和已验证能力状态，不返回本机路径与密钥信息 |
| `GET` | `/projects` | 可用 | 项目列表 |
| `POST` | `/projects` | 可用 | 创建项目，提交 Brief 和可选模型策略 |
| `GET` | `/projects/{project_id}` | 可用 | 项目详情、进度和待审批信息 |
| `GET` | `/projects/{project_id}/agents` | 可用 | Agent Run 列表与模型调用审计摘要 |
| `GET` | `/projects/{project_id}/events` | 可用 | SSE 实时事件和历史回放 |
| `POST` | `/projects/{project_id}/decisions` | 可用 | 提交当前 Human Gate 决定 |
| `GET` | `/projects/{project_id}/source-requirements` | 可用 | 实时查询目标/竞品范围和各研究维度的资料准备度、缺口与补充动作 |
| `PUT` | `/projects/{project_id}/source-requirements/scope` | 可用 | 保存目标产品、竞品、研究维度及 actor/reason，并立即重新评估 |
| `POST` | `/projects/{project_id}/source-discovery/searches` | 可用 | 调用已注册搜索 Provider；返回候选线索或可审计的 blocked/failed 状态，不创建 Evidence |
| `GET` | `/projects/{project_id}/source-discovery/searches` | 可用 | 查询项目内搜索发现历史和候选来源 |
| `GET` | `/projects/{project_id}/source-discovery/searches/{search_discovery_run_id}` | 可用 | 查询单次搜索状态、错误分类和 `candidate_only` 结果 |
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
| `GET` | `/projects/{project_id}/claims` | 可用 | Claim 与支持/反对 Evidence IDs |
| `GET` | `/projects/{project_id}/innovations` | 可用 | 候选机会、事件理解、评分和红队结果 |

查询接口只返回数据库中已经存在的记录。证据不足时会返回空列表或明确状态，不会自动生成占位 Evidence、Claim 或 Innovation。

### 3.1 当前仍是骨架的接口

| 方法 | 路径 | 当前行为 | 前端处理方式 |
|---|---|---|---|
| `GET` | `/projects/{project_id}/concepts` | `501 Not Implemented` | 新页面改用 `/innovations`；旧 Concept 页面只作为待迁移 UI |
| `GET` | `/projects/{project_id}/report` | `501 Not Implemented` | 展示“报告尚未生成”，不要把 Mock 报告标成真实结果 |
| `GET` | `/projects/{project_id}/metrics` | `501 Not Implemented` | 展示空状态或明确的演示数据标识 |

以下目标能力尚无当前 `/api/v1` 生产接口：

- AI 连续追问和自动生成 Research Brief；
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

最近一次后端完整验证：

```text
pytest: 175 passed
ruff: passed
mypy: passed（145 个源文件）
Alembic: 空数据库升级到 0011_search_discovery、降级到 0010 后再次升级通过
真实模型：GLM 5.2 与 DeepSeek V4 Pro 基础探针、资料路由及官方产品专家完整网页链路冒烟测试通过
外部 Runtime：OpenCode 1.18.15 + GLM 5.2 结构化 ResearchArtifact 冒烟测试通过
搜索 Provider：Tavily HTTP 契约、错误分类和安全边界由 MockTransport 验证；本机尚未配置 TAVILY_API_KEY，因此未声称真实联网搜索通过
```

接下来的后端开发顺序应先补齐自动竞品发现，再继续剩余竞品专家和领域分析：

```text
Search Discovery Connector（已完成）
→ Competitor Discovery Agent & Candidate Gate
→ Competitor Source Onboarding
→ Source Requirements Re-evaluation
→ Competitor Price & Channel Specialist
→ Competitor User Review Specialist
→ Competitor Synthesis & Evidence Audit
→ Product Technical Agent
→ Commercial Agent
→ Red Team Revision
→ Package Risk Demo
→ Feishu Integration
→ E2E Hardening
```
