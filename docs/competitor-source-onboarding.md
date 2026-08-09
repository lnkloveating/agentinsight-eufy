# 竞品候选来源接入

## 目标

该模块把 Candidate Gate 已确认的竞品候选 URL 登记为统一资料中心中的授权 Source Asset，
解决“用户已经确认竞品以后，候选网页怎样进入真实证据管道”的问题。

```text
confirmed Competitor Discovery Artifact
→ 读取 Gate 选择的 proposal
→ 自动定位 proposal 引用的 candidate URL
→ 用户确认公开资料研究授权
→ URL 再次安全规范化和项目内去重
→ Source Asset + queued Collection Job
→ 保存 Artifact / Decision / Proposal / Candidate / Source Asset 血缘
```

Onboarding 不访问网页，不运行 OpenCode，不调用模型，不解析正文，也不创建 Evidence。后续仍需
依次执行 Web Processing、Source Routing、片段审核和 Evidence 晋级。

## 前置门禁

一次接入必须同时满足：

- Artifact 属于当前项目和 `task_competitor_discovery`；
- Candidate Gate 已执行 `confirm`，不能使用 pending、reject 或 revision Artifact；
- 只使用 Gate 的 `selected_proposal_ids`，前端不能在接入时偷偷增加候选；
- 所选 proposal 和 candidate ID 仍存在于不可变 Artifact；
- 当前正式竞品范围仍包含所选准确产品，范围变化时拒绝陈旧接入；
- URL 再次通过公开 HTTP/HTTPS 校验，规范化域名必须与 Artifact 记录一致；
- 用户提交 `authorization_confirmed=true`，授权依据固定为 `publicly_available`。

## 原子性、幂等和血缘

同一 Artifact 最多创建一个 Onboarding 批次。批次中的 Source Asset、Collection Job、血缘项和
项目事件在同一数据库事务中保存；失败不会留下半批数据。重复请求返回原批次并使用 HTTP
200。不同候选指向同一规范化 URL 时复用一个 Source Asset；项目中已经存在的授权链接也会
复用，不覆盖原授权元数据。软删除过的相同链接可以恢复并创建新的 queued Collection Job。

每个 Onboarding Item 保存：

```text
artifact_id
decision_id
proposal_id
candidate_id
exact product
source_asset_id
whether the Source Asset was newly created
```

因此后续资料准备度和领域 Agent 可以使用结构化血缘，不必依靠网页标题猜测它属于哪个竞品。

## API

```text
POST /api/v1/projects/{project_id}/competitor-source-onboardings
GET  /api/v1/projects/{project_id}/competitor-source-onboardings
```

前端应在 Candidate Gate 确认成功后显示“接入已确认来源”操作，并要求用户确认公开资料授权。
响应中的 Source Asset 应进入统一资料列表，初始处理状态为 `queued`。页面不能把
`onboarding.status=completed` 理解为网页解析完成或 Evidence 已就绪；它只表示登记事务完成。

## 自动化与真实验证

- `tests/unit/test_competitor_source_onboarding_contracts.py`：公开授权和审计字段；
- `tests/integration/test_competitor_source_onboarding_api.py`：Gate、范围、项目隔离、URL 去重、
  幂等、Collection Job、事件和零 Evidence；
- `scripts/smoke_competitor_source_onboarding_live.py`：真实 Tavily、主办方模型、人工确认模拟和
  Source Asset 接入的临时数据库链路。
