# 后端开发说明

后端 `/api/v1` 已经实现项目生命周期、Agent 运行记录、人工决定、持久化事件、SSE 断线续传，以及 SourceAsset、Evidence、Claim、Innovation、LangGraph 编排底座、Agent Runtime Core、多模型 Model Gateway 和安全的外部 CLI Runtime。SourceAsset 解析管线、领域 Agent、Demo 和飞书集成将在后续增量中接入同一数据与事件体系。

`docs/api/openapi.yaml` 当前描述 `/api/v2` 目标契约，不代表 v2 路由已经实现。开发顺序以 `docs/research-flow.md`、`docs/agent-contracts.md`、`docs/state-machine.md` 和 `docs/acceptance-criteria.md` 为准。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.main
```

Swagger：`http://localhost:8000/docs`

## 配置主办方模型路由

主办方文档提供 `https://ai-router-cn-pub.anker-in.com/chat/completions`。当前后端按文档明确的 OpenAI 协议接入以下两个模型：

- `hackathon/v_model/glm-5.2`；
- `hackathon/v_model/deepseek-v4-pro`。

在 `src/backend` 下创建本地 `.env`，复制仓库根目录 `.env.example` 的非敏感配置，并只在本地填写 `ANKER_ROUTER_API_KEY`。`.env` 已被 Git 忽略，API Key 不得写入 `.env.example`、模型目录 JSON、数据库或运行日志。

带 `anthropic-` 前缀的模型由主办方定义为 Anthropic 协议；在对应 HTTP 路径和请求契约确认前不注册到当前 OpenAI-compatible Provider，避免用错误协议调用。

## 配置外部 OpenCode Runtime

安装官方 CLI：

```powershell
npm install -g opencode-ai@latest
opencode --version
```

后端通过 `ExternalCliAgentAdapter` 启动固定注册的 OpenCode Driver，不接受 API 请求提交任意命令。每次运行使用 `EXTERNAL_RUNTIME_WORKSPACE_ROOT` 下的项目/Agent Run 隔离目录；只向子进程注入配置指定的凭据，原始 stdout/stderr 不写日志，非零退出的错误文本会先脱敏。

OpenCode 当前只声明 `text`、`structured_output` 和 `local_files`。Driver 明确禁止 bash、编辑、外部目录、网页访问和子 Agent，因此不能把“OpenCode 可用”解释成“已经支持网站或视频解析”。前端通过 `GET /api/v1/runtimes` 获取真实安装、凭据、版本和能力状态。

本地真实模型冒烟：

```powershell
python scripts/smoke_external_cli_runtime.py
```

脚本读取被 Git 忽略的 `src/backend/.env`，只输出 Runtime 版本、模型 ID 和 Artifact 摘要，不输出凭据。

## 创建中文 eufy 演示项目

在仓库根目录执行：

```powershell
python scripts/seed_demo_project.py
```

演示项目 ID 固定为 `proj_demo_eufy`，种子脚本可重复执行，不会产生重复数据。

## 当前 v1 可用接口

```text
POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{project_id}
GET  /api/v1/projects/{project_id}/agents
GET  /api/v1/projects/{project_id}/events
POST /api/v1/projects/{project_id}/sources/files
POST /api/v1/projects/{project_id}/sources/links
GET  /api/v1/projects/{project_id}/sources
GET  /api/v1/projects/{project_id}/sources/{source_asset_id}
DELETE /api/v1/projects/{project_id}/sources/{source_asset_id}
GET  /api/v1/projects/{project_id}/evidence
GET  /api/v1/projects/{project_id}/claims
GET  /api/v1/projects/{project_id}/innovations
GET  /api/v1/models
GET  /api/v1/runtimes
POST /api/v1/projects/{project_id}/decisions
```

SSE 会先回放数据库历史事件，再等待实时通知；客户端可以通过 `Last-Event-ID` 恢复断线后的事件。

## v2 实现顺序

1. Evidence、Collection Job 和 Claim Gate（已完成基础实现）；
2. Innovation、评分和红队结果（已完成基础实现）；
3. LangGraph 主图、Checkpoint 与三个 Human Gate（已完成 Foundation）；
4. Agent Runtime Core、外部 CLI Adapter、运行记录、版本化 Artifact、超时与取消（已完成；等待业务 Agent 绑定和任务启动 API）；
5. Model Gateway、多模型选择、Prompt 版本、Token/成本和 Provider 边界（框架已完成；等待真实 Provider 凭据验证）；
6. Source Ingestion、项目隔离存储、授权审计和待解析 Collection Job（已完成）；
7. Evidence Processing Pipeline，把 SourceAsset 安全投递给已验证的外部 Runtime；
8. Package Risk Intelligence Demo Result；
9. 飞书五个 Aily API Skill、卡片决定和结果沉淀；
10. v2 契约、集成和端到端测试全部通过后再启用 `/api/v2` 路由。

Evidence Foundation 的自动化验收映射：

- AC-04：`test_evidence_normalization.py`、`test_evidence_ingestion.py`、`test_collection_job_failure.py` 和 `test_evidence_query_api.py`；
- AC-04 原始资料入口：`test_source_validation.py` 和 `test_source_ingestion_api.py` 验证授权、类型/大小限制、私网 URL、哈希去重、项目隔离、文件删除、任务阻断和恢复；
- AC-05：`test_claim_gate.py` 和 `test_claim_gate_persistence.py`。

Innovation Foundation 的自动化验收映射：

- AC-06：`test_innovation_rules.py` 和 `test_innovation_service.py`；
- AC-07：`test_innovation_rules.py` 和 `test_innovation_query_api.py`；
- AC-08：`test_innovation_rules.py` 和 `test_innovation_service.py`。

候选场景查询只返回后端已经持久化的 Agent 产物；证据不足时返回明确缺口或空列表，不会由接口自动补造候选，也不会接受 Mock Evidence 作为候选依据。

LangGraph Foundation 的自动化验收映射：

- AC-03：`test_research_workflow.py::test_complete_graph_pauses_at_three_gates_and_runs_all_agents`；
- AC-07：`test_research_workflow.py::test_evidence_gap_has_bounded_research_loop_and_no_fake_candidates`；
- AC-09：`test_research_workflow.py::test_complete_graph_pauses_at_three_gates_and_runs_all_agents` 和 `test_workflow_contracts.py`；
- AC-11：`test_research_workflow.py::test_sqlite_checkpoint_retries_only_failed_parallel_node` 和 `test_scenario_research_more_reruns_only_affected_research_agent`。

工作流主图已经预留调研总管、用户研究、竞品 A2A 边界、产品技术、商业、红队、候选综合、验证分发和最终综合节点。生产默认使用 `UnboundAgentRuntime`：没有绑定真实 Runtime 时明确返回 `AGENT_RUNTIME_NOT_BOUND`，不会产生占位研究结果。`tests/integration/workflow_runtime.py` 中的确定性 Runtime 仅用于验证编排和 Checkpoint，不会被生产代码导入。

Agent Runtime Core 的自动化验收映射：

- AC-03：`test_runtime_langgraph_integration.py` 验证九个角色通过持久化 Runtime 执行完整主图；
- AC-11：`test_agent_runtime_gateway.py` 验证超时、取消、错误分类和失败时不保存 Artifact，并由现有 Checkpoint 测试覆盖恢复；
- AC-13：`test_agent_runtime_gateway.py` 验证独立 Agent Run、连续 Runtime Event、Artifact 版本、输入血缘和项目隔离。

`AgentRuntimeGateway` 只负责统一调用、校验和持久化，通过 `AgentRegistry` 显式绑定 Adapter；未绑定角色会明确失败。`InternalModelAgentAdapter` 已接入 Model Gateway，但只有业务分支显式注册 Prompt 且真实 Provider 已绑定时才能执行。`ExternalCliAgentAdapter` 与 OpenCode Driver 已完成真实模型冒烟，但尚未绑定具体领域 Agent，也尚未自动读取 SourceAsset。A2A Adapter 属于后续分支。测试 Driver 和测试 Evidence 只存在于 `tests/`，不会进入生产运行路径。

External CLI Runtime 的自动化验收映射：

- AC-04：`test_external_cli_process.py` 验证环境隔离、输出上限、超时、取消和健康探测；
- AC-04：`test_opencode_driver.py` 验证只读权限、密钥引用、隔离工作区和 JSON/JSONL 解码；
- AC-11/AC-13：`test_external_cli_adapter.py` 验证真实 OS 子进程、Gateway 持久化、失败分类、密钥脱敏和失败不保存 Artifact；
- Deep Research Web Runtime 选择接口：`test_runtime_catalog_api.py` 验证可用状态、能力声明和敏感配置不出现在 API 响应。

Model Gateway 的自动化验收映射：

- AC-03：`test_internal_model_adapter.py` 验证 Agent 级模型覆盖、结构化 `ResearchArtifact` 和缺 Prompt 明确失败；
- AC-11：`test_model_gateway.py` 验证限流重试、超时、无效结构化输出和缺凭据失败；
- AC-13：`test_model_gateway.py` 验证 Model Call、Provider、Prompt 版本、Token、成本和 Agent Run 关联审计；
- Deep Research Web 模型选择接口：`test_model_catalog_api.py` 验证模型目录、项目选择和密钥不出现在 API 响应。
- OpenAI-compatible Provider：`test_openai_compatible_provider.py` 验证 Chat Completions 请求、结构化模式、用量解析及 401、429、5xx 错误分类。

`MODEL_CATALOG_JSON` 只配置模型元数据和密钥所在的环境变量名。API Key 值只从本地 `.env`、部署环境变量或 Secret Manager 读取，不进入数据库、事件、Artifact 或 API 响应。当前生产 Provider Registry 默认为空，不会用测试 Provider 或假响应兜底；绑定真实 Provider 并完成本地联网冒烟测试后才能推送该分支。

## 测试

```powershell
pytest
ruff check .
mypy app
```
