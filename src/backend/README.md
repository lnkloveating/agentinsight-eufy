# 后端开发说明

后端 `/api/v1` 已经实现项目生命周期、Agent 运行记录、人工决定、持久化事件、SSE 断线续传，以及 Evidence、Claim、Innovation 和 LangGraph 编排基础能力。真实 Agent Runtime、模型、数据连接器、Demo 和飞书集成将在后续增量中接入同一数据与事件体系。

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
GET  /api/v1/projects/{project_id}/evidence
GET  /api/v1/projects/{project_id}/claims
GET  /api/v1/projects/{project_id}/innovations
POST /api/v1/projects/{project_id}/decisions
```

SSE 会先回放数据库历史事件，再等待实时通知；客户端可以通过 `Last-Event-ID` 恢复断线后的事件。

## v2 实现顺序

1. Evidence、Collection Job 和 Claim Gate（已完成基础实现）；
2. Innovation、评分和红队结果（已完成基础实现）；
3. LangGraph 主图、Checkpoint 与三个 Human Gate（已完成 Foundation；等待 Runtime 和 API 生命周期接线）；
4. Package Risk Intelligence Demo Result；
5. 飞书五个 Aily API Skill、卡片决定和结果沉淀；
6. v2 契约、集成和端到端测试全部通过后再启用 `/api/v2` 路由。

Evidence Foundation 的自动化验收映射：

- AC-04：`test_evidence_normalization.py`、`test_evidence_ingestion.py`、`test_collection_job_failure.py` 和 `test_evidence_query_api.py`；
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

## 测试

```powershell
pytest
ruff check .
mypy app
```
