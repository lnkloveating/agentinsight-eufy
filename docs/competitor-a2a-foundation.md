# 竞品 A2A 运行底座与前端联调说明

## 当前实现的边界

本分支已经把现有 LangGraph 中的 `competitor_research` 节点接到统一 Agent Runtime 的
`CompetitorA2ASupervisorAdapter`。主管会把一个竞品研究任务稳定拆成三个并行子任务：

```text
Competitor Supervisor
├─ Official Product Specialist
├─ Price & Channel Specialist
└─ User Review Specialist
```

三个子任务只通过 `EvidenceRequest` 描述需要寻找和分析的证据，不包含预设竞品事实。
每个子任务都有独立的数据库记录、状态、attempt、trace、输入 Hash、错误分类和
Evidence IDs。

当前生产启动只注册了竞品主管，没有注册三个真实专家。因此实际执行时会明确得到
`blocked / specialist_not_bound`，不会用测试 Adapter、Mock 数据或大模型常识生成竞品
结果。真实专家的 Prompt、模型调用和差异化综合属于后续分支。

## 已实现的恢复语义

- 三个已绑定专家并行执行；
- 相同任务范围、Evidence Context 和上游 Artifact 对应相同输入 Hash；
- 专家成功交付后，重试主管会复用该专家结果；
- 失败、超时或无效交付物不会留下成功输出；
- 再次运行时只重跑失败的专家；
- 输入发生变化时，旧专家结果不会被复用；
- 事实性 `finding` 缺少 Evidence ID、引用当前上下文外证据或使用不允许的
  Claim 类型时，任务按 `artifact_invalid` 失败。

## 前端当前可以消费的状态

本分支没有新增公共 HTTP API，因此 `docs/api/openapi.yaml` 无需变化。父级竞品主管仍会
作为普通 Agent Run 出现在：

```http
GET /api/v1/projects/{project_id}/agents
```

A2A 子任务会写入项目事件并通过既有 SSE 流发送：

```text
a2a_task_started
a2a_task_completed
a2a_task_failed
a2a_task_blocked
a2a_task_reused
```

事件中可展示的安全字段包括：

```text
a2a_task_id
parent_agent_run_id
parent_task_id
specialist_type
adapter_type
status
attempt_number
error_code
retryable
evidence_count
```

因此前端可以先把竞品主管展开为三个专家泳道，支持 `running`、`completed`、`failed`、
`blocked` 和 `reused` 展示。当前没有 A2A Task 查询接口，刷新后的完整子任务列表功能应
等待后续统一运行投影 API；项目事件历史仍可恢复时间线。

## 当前没有实现的能力

- 三个专家的真实模型 Adapter 和业务 Prompt；
- 自动检索网页或绕过网站反爬；
- 竞品能力矩阵、差异化结论和 Evidence 覆盖审计；
- 用户选择具体竞品专家模型的公共 API；
- A2A Task 独立查询、取消和人工重试 API；
- 产品技术、商业、红队和最终报告逻辑。

## 后续建议拆分

为避免把大量领域判断堆入一个分支，建议继续拆成：

```text
agent/competitor-official-product
→ agent/competitor-price-channel
→ agent/competitor-user-review
→ agent/competitor-synthesis
```

前三个分支各自实现 Prompt、Evidence 过滤、结构化输出和质量测试；最后一个分支才建立
竞品能力矩阵、差异化综合和证据覆盖审计。所有分支继续遵守“没有 Evidence ID 就没有
事实结论”。

## 自动化测试

- `tests/unit/test_competitor_a2a_contracts.py`：契约和引用规则；
- `tests/integration/test_competitor_a2a_gateway.py`：并行、blocked、超时、证据拒绝和定向恢复；
- `tests/integration/test_competitor_a2a_supervisor.py`：主管拆分与统一 Runtime 接线；
- `tests/integration/test_runtime_langgraph_integration.py`：外层 LangGraph Checkpoint 恢复。

