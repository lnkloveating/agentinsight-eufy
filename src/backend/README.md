# 后端开发说明

后端 `/api/v1` 已经实现项目生命周期、Agent 运行记录、人工决定、持久化事件、SSE 断线续传，以及 SourceAsset、Evidence、Claim、Innovation、LangGraph 编排底座、Agent Runtime Core 和多模型 Model Gateway 框架。外部资料解析 Runtime、领域 Agent、Demo 和飞书集成将在后续增量中接入同一数据与事件体系。

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
POST /api/v1/projects/{project_id}/decisions
```

SSE 会先回放数据库历史事件，再等待实时通知；客户端可以通过 `Last-Event-ID` 恢复断线后的事件。

## v2 实现顺序

1. Evidence、Collection Job 和 Claim Gate（已完成基础实现）；
2. Innovation、评分和红队结果（已完成基础实现）；
3. LangGraph 主图、Checkpoint 与三个 Human Gate（已完成 Foundation）；
4. Agent Runtime Core、运行记录、版本化 Artifact、超时与取消（已完成；等待真实 Adapter 和 API 生命周期接线）；
5. Model Gateway、多模型选择、Prompt 版本、Token/成本和 Provider 边界（框架已完成；等待真实 Provider 凭据验证）；
6. Source Ingestion、项目隔离存储、授权审计和待解析 Collection Job（已完成）；
7. 外部 Runtime Adapter 与 Evidence Processing Pipeline；
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

`AgentRuntimeGateway` 只负责统一调用、校验和持久化，通过 `AgentRegistry` 显式绑定 Adapter；未绑定角色会明确失败。`InternalModelAgentAdapter` 已接入 Model Gateway，但只有业务分支显式注册 Prompt 且真实 Provider 已绑定时才能执行。外部 Runtime Adapter 和 A2A Adapter 属于后续分支。测试 Adapter 和测试 Evidence 只存在于 `tests/`，不会进入生产运行路径。

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
