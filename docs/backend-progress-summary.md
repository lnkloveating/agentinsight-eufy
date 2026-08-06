# 后端进度与前端适配说明

> 更新时间：2026-08-07
>
> 基线分支：`main`
>
> 基线提交：`a415310`（合并多模型网关与主办方模型路由）

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

> 项目生命周期、证据和候选场景数据底座、LangGraph 编排底座、Agent Runtime Core、多模型 Model Gateway 已经完成；真实数据连接器和领域 Agent 尚未开始完整接线，因此系统还不能自动完成一整轮真实行业调研。

### 2.1 已完成并合并到 `main`

| 模块 | 当前能力 | 对前端的意义 |
|---|---|---|
| 项目生命周期 | 创建/查询项目、Brief 人工审批、状态迁移、持久化事件 | 可以实现项目列表、Brief 确认页和审批面板 |
| SSE 事件 | 历史事件回放、实时事件、断线续传游标、心跳 | 可以实现实时研究时间线和连接状态 |
| Evidence Foundation | Evidence、Collection Job、Claim、去重、跨项目隔离、Claim Gate、失败记录 | 可以实现 Evidence Center 和 Claim-Evidence 关系展示 |
| Innovation Foundation | 事件理解结构、八维评分、红队结果、候选组合门禁、持久化查询 | 可以实现候选机会比较页，不应继续只依赖旧 `Concept` 类型 |
| LangGraph Foundation | 研究共享状态、并行研究节点、Checkpoint、三个 Human Gate、定向重跑 | 可以按目标流程设计节点图和 Gate UI，但当前 HTTP 流程不会自动跑完整真实 Agent |
| Agent Runtime Core | Agent Run、Adapter Registry、Artifact Store、超时、取消、错误分类、运行隔离、运行事件 | 可以展示 Agent 状态、错误、Artifact 元数据和运行历史 |
| Model Gateway | 模型目录、项目默认模型、Agent 级覆盖、Prompt 版本、结构化输出、重试、Token/成本审计 | 可以实现模型选择器和 Agent 调用审计展示 |
| 主办方模型路由 | 已接入 GLM 5.2 与 DeepSeek V4 Pro，并完成真实联网冒烟测试 | 前端只使用 `/models` 返回的 `model_id`，不接触 API Key |

### 2.2 已完成底座、但还没有形成完整业务运行

以下能力在内部服务和自动化测试中已经成立，但前端不能误认为“创建项目后就会自动生成完整报告”：

1. LangGraph 主图能够在测试 Runtime 下完成并行节点、三次暂停和 Checkpoint 恢复。
2. Agent Runtime 能够调用显式注册的 Adapter，并保存 Agent Run 与版本化 Artifact。
3. `InternalModelAgentAdapter` 能够通过 Model Gateway 调用真实模型。
4. Evidence 和 Innovation 服务可以保存、校验和查询真实持久化记录。

当前仍缺少：

- HTTP 项目生命周期与 LangGraph 完整启动/恢复的生产接线；
- 用户研究、竞品、产品技术、商业和红队等业务 Prompt；
- 真实 Evidence Connectors；
- 竞品 A2A Runtime；
- 最终报告、Package Risk Demo 和飞书集成。

生产环境没有注册业务 Prompt 或真实业务 Adapter 时会明确失败，不会用 Mock 结果冒充调研完成。

## 3. 当前真实可用的 `/api/v1` 接口

| 方法 | 路径 | 状态 | 前端用途 |
|---|---|---|---|
| `GET` | `/health` | 可用 | 服务健康状态 |
| `GET` | `/models` | 可用 | 模型选择器；返回安全模型目录和凭据可用状态 |
| `GET` | `/projects` | 可用 | 项目列表 |
| `POST` | `/projects` | 可用 | 创建项目，提交 Brief 和可选模型策略 |
| `GET` | `/projects/{project_id}` | 可用 | 项目详情、进度和待审批信息 |
| `GET` | `/projects/{project_id}/agents` | 可用 | Agent Run 列表与模型调用审计摘要 |
| `GET` | `/projects/{project_id}/events` | 可用 | SSE 实时事件和历史回放 |
| `POST` | `/projects/{project_id}/decisions` | 可用 | 提交当前 Human Gate 决定 |
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
- 外部 Runtime、竞品 A2A 和真实数据采集任务控制。

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

### 4.2 `Project` 类型

当前后端 `Project` 比前端类型多一个字段：

```text
model_selection: ModelSelection | null
```

前端应保留该字段，用于项目详情和模型审计展示。

### 4.3 `AgentRun` 类型

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

### 4.4 `Evidence` 类型

当前前端类型与真实后端存在字段名差异：

| 前端旧字段 | 后端真实字段 |
|---|---|
| `excerpt` | `original_excerpt` |
| `captured_at` | `collected_at` |

后端还返回 `source_domain`、`claim_type`、`product`、`region`、`user_segment`、`published_at`、`authority_score`、`recency_score` 和 `diversity_score`。Evidence Center 应以真实后端字段为准。

### 4.5 `Claim` 类型

除现有字段外，后端还返回：

```text
claim_type
scope
```

Claim 状态包括 `proposed`、`supported`、`disputed`、`missing_evidence`、`rejected` 和 `unknown`。

### 4.6 使用 `Innovation` 替代旧 `Concept`

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

### 4.7 SSE 当前行为

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

### P1：可以先设计、等待真实数据接入

1. Deep Research 输入和 Brief 确认页面。
2. Agent 运行时间线、并行节点和错误恢复展示。
3. Evidence Center、来源筛选和 Claim-Evidence 下钻。
4. Innovation 候选竞技场、评分雷达和红队意见。
5. 三个 Human Gate 的审批面板。
6. Package Risk 交互 Demo 原型。

这些页面可以使用明确标识为 `DEMO SAMPLE` 的展示数据完成布局，但不能在 UI 中把它们表示为后端真实研究结果。

## 7. 本地联调

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

## 8. 验证状态与下一步后端计划

最近一次后端完整验证：

```text
pytest: 67 passed
ruff: passed
mypy: passed（86 个源文件）
真实模型：GLM 5.2 与 DeepSeek V4 Pro 冒烟测试通过
```

接下来的后端开发顺序应从真实数据接入开始：

```text
Evidence Connectors
→ Crawler Fallback
→ User Research Agent
→ Competitor A2A
→ Product Technical Agent
→ Commercial Agent
→ Red Team Revision
→ Package Risk Demo
→ Feishu Integration
→ E2E Hardening
```

其中前端最先会受到 `Evidence Connectors`、领域 Agent 和 Package Risk Demo 三个阶段的数据契约影响；新增公共接口时以后端先更新 OpenAPI 和契约测试为准。
