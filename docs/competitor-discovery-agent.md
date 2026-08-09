# 竞品候选发现 Agent

## 目标与边界

该 Agent 解决的是“这些公开搜索结果里，哪些准确产品值得作为待确认竞品”，不是“竞品有
哪些功能或价格”。它只消费成功的 `competitor_candidate` Search Discovery Run，输出版本化
候选 Artifact，并暂停在 Candidate Gate。

```text
确认目标产品准确型号
→ Tavily Search Discovery（candidate_only）
→ Competitor Discovery Agent
→ 确定性 candidate_id / 品牌型号 / 目标范围校验
→ Candidate Gate
→ 用户确认后更新正式竞品范围
→ Competitor Source Onboarding
→ 网页处理、路由、片段审核和 Evidence 晋级
```

搜索标题和摘要仍然不是 Evidence。候选 Artifact 的 `evidence_ids` 固定为空；即使模型给出
高置信度，也不能满足 Source Requirements，不能进入竞品事实矩阵，更不能出现在最终报告
中。真实功能、价格、评价等事实必须由后续资料接入和 Evidence Gate 建立。

## 输入与确定性门禁

运行前必须满足：

- 项目已通过 Research Brief 审批；
- Source Requirement Scope 至少包含一个带准确型号的目标产品；
- 输入运行属于当前项目、状态为 `succeeded`、intent 为 `competitor_candidate`；
- 单次最多接收 5 个 Search Run 和 50 个去重候选。

模型必须处理每个输入 `candidate_id`，每个 ID 恰好出现在一个提名或排除组中。后端在保存
前确定性拒绝以下输出：

- 编造、遗漏或重复使用 candidate ID；
- 把目标产品提名为自身竞品；
- 重复产品；
- 品牌、型号或变体没有在引用候选的标题/摘要中明确出现；
- 输出不符合固定结构化 Schema。

达到请求的准确候选数量时 Artifact 为 `completed`；有候选但数量不足时为 `partial`；没有
准确候选时为 `blocked`。`blocked` 是可信的研究结果，系统不得为了凑数量编造竞品。

## Candidate Gate

```text
pending
├─ confirm：选择至少一个 proposal，原子合并到正式 competitor scope
├─ reject：保留 Artifact 和审计，不修改 scope
└─ request_revision：保留返工要求，不修改 scope
```

每个 Artifact 只能决定一次。确认时后端会再次检查目标产品范围没有变化，并通过现有
`SourceRequirementScopeUpdate` 规则验证目标与竞品不重叠、产品不重复、总数不超限。决定
保存 actor、reason、时间和项目事件。新的 Agent 运行会生成新的 Artifact 版本，不覆盖历史。

## API

```text
POST /api/v1/projects/{project_id}/agents/competitor-discovery
GET  /api/v1/projects/{project_id}/agents/competitor-discovery/artifacts
POST /api/v1/projects/{project_id}/agents/competitor-discovery/artifacts/{artifact_id}/decision
```

前端应先展示 Search Run 的候选来源，再展示 Agent 提名、排除理由、未知项、覆盖率、运行模型
和 Gate 状态。`pending` 前不能把候选显示成已确认竞品；确认后应刷新
`/source-requirements`，并调用 `/competitor-source-onboardings` 接入已确认来源，而不是直接
显示竞品结论。

模型选择继承项目的 `competitor_research` Agent 覆盖。单次模型调用与整个 Runtime 使用独立
超时预算，默认分别为 180 秒和 600 秒，因此 Model Gateway 的有限重试不会被外层提前取消。

## 自动化与真实联调

- `tests/unit/test_competitor_discovery_contracts.py`：candidate ID、准确型号、目标重叠和质量门禁；
- `tests/integration/test_competitor_discovery_agent.py`：Model Gateway、Prompt、模型选择、
  Agent Run、Model Call 和零 Evidence 持久化；
- `tests/integration/test_competitor_discovery_api.py`：项目隔离、Gate 前后范围、幂等冲突与事件；
- `scripts/smoke_competitor_discovery_live.py`：使用本地未提交凭据运行 Tavily 和主办方模型，
  并验证候选仍停在 Gate。

真实冒烟允许返回 `blocked`：这表示 Provider 和模型链路真实运行成功，但当前搜索候选没有
足够明确的准确型号。它不能被改写为成功发现竞品，也不应使用 Mock 补齐。
