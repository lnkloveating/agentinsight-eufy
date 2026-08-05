# AgentInsight × eufy

AI 原生产品定义工作台的比赛级工程。仓库已经具备 FastAPI/React 启动入口、项目生命周期、人工决定、数据库事件和 SSE 骨架；Evidence、六 Agent 工作流、事件理解 Demo 和飞书集成仍按目标契约增量实现。

## 产品目标

围绕“北美家庭安防中哪些高频事件值得从检测通知升级为事件理解”完成一条可追溯链路：

1. 用户在飞书 Aily 中澄清并确认结构化 Research Brief；
2. 六类 Agent 基于共享 Evidence Lake 执行用户、竞品、产品技术、商业和红队研究；
3. 系统比较至少三个事件理解候选，并保存证据、评分和淘汰理由；
4. 用户在飞书批准一个合格候选进入可运行 Demo；
5. 首选候选 Package Risk Intelligence 融合包裹状态、家庭状态和外部风险信号；
6. 系统输出建议立项、补充验证或不建议立项，并保留完整证据和人工决定。

## 技术边界

- 前端：React、TypeScript、Vite，位于 `src/frontend`；
- 后端：FastAPI、Python，位于 `src/backend`；
- API 契约：OpenAPI 3.1；现有运行时为 `/api/v1`，`docs/api/openapi.yaml` 定义待实现的 `/api/v2` 目标；
- 编排预留：LangGraph；
- 集成预留：飞书 Aily、A2A、MCP、AgentInsight；
- 质量保障：单元测试、集成测试、契约测试、端到端验收和 CI。

## 目录

```text
agentinsight-eufy/
├─ .github/                 GitHub 模板与 CI
├─ docs/                    架构、验收、API 和决策记录
├─ infra/                   Docker 与部署占位
├─ scripts/                 本地开发与校验脚本
├─ src/
│  ├─ backend/              FastAPI 后端
│  ├─ frontend/             企业级前端
│  └─ shared/               跨端契约说明
└─ tests/                   跨系统契约与验收场景
```

## 起始入口

后端入口：`src/backend/app/main.py` 中的 `create_app()` 和 `main()`。

前端入口：`src/frontend/src/main.tsx` 中的 `main()`。

本地启动后，Swagger UI 计划位于：`http://localhost:8000/docs`。

## 文档导航

| 文档 | 作用 |
|---|---|
| `docs/research-flow.md` | 统一行业机会、候选场景、飞书位置和 Package Demo 逻辑 |
| `docs/agent-contracts.md` | 六类 Agent 的职责、Schema、依赖、评分和返工规则 |
| `docs/state-machine.md` | 项目状态与 Brief、场景、最终建议三个人工 Gate |
| `docs/architecture.md` | 系统边界、飞书协作层和工作流依赖 |
| `docs/api/openapi.yaml` | `/api/v2` 目标公共契约 |
| `docs/acceptance-criteria.md` | MVP 验收和 Release Gate |
| `tests/acceptance/features/end_to_end.feature` | 中文端到端行为场景 |
| `eufy调研报告.md` | 竞赛开题、研究依据和总体设计说明 |

## 当前状态

- [x] 工程目录
- [x] 统一研究流程和六 Agent 结构化契约
- [x] `/api/v2` 目标 OpenAPI 契约
- [x] 新流程验收标准和端到端场景
- [x] 前后端启动入口
- [x] v1 项目生命周期、人工决定、数据库事件和 SSE 骨架
- [x] 首个项目生命周期数据库迁移
- [ ] v2 Evidence、Claim、Innovation 和 Demo 持久化
- [ ] 六 Agent LangGraph 工作流与 Checkpoint 恢复
- [ ] 飞书 Aily、卡片、多维表格和文档集成
- [ ] AgentInsight 与本地完整 Trace

## 协作原则

接口优先。当前前端和后端继续使用已实现的 `/api/v1`；新业务按 `docs/api/openapi.yaml` 的 `/api/v2` 目标契约实现。v2 路由只有在实现、迁移和契约测试完成后才可对外宣告可用，Mock 数据不得冒充真实研究结果。
