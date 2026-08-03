# AgentInsight × eufy

AI 原生产品定义工作台的比赛级工程骨架。本仓库当前只定义边界、目录、接口契约、验收标准和启动入口，不包含业务实现。

## 产品目标

围绕“北美租房用户的家庭安防机会”完成一条可追溯的端到端链路：

1. 创建结构化研究任务；
2. 多 Agent 执行用户、竞品、技术和商业研究；
3. 证据进入共享 Evidence Lake；
4. 生成、质疑和淘汰候选概念；
5. 在人工审批节点暂停与恢复；
6. 输出带证据引用的产品提案和方法对照结果。

## 技术边界

- 前端：React、TypeScript、Vite，位于 `src/frontend`；
- 后端：FastAPI、Python，位于 `src/backend`；
- API 契约：OpenAPI 3.1，位于 `docs/api/openapi.yaml`；
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

## 当前状态

- [x] 工程目录
- [x] OpenAPI 契约
- [x] 验收标准
- [x] 前后端启动入口
- [x] CI、测试和部署目录
- [ ] 业务逻辑
- [ ] 数据库迁移
- [ ] Agent 工作流
- [ ] 飞书与观测集成

## 协作原则

接口优先。前端基于 `docs/api/openapi.yaml` 和 Mock 数据并行开发；后端在不破坏契约的前提下逐步将占位实现替换为真实工作流。
