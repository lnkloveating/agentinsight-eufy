# Fragment Evidence Pipeline

这个阶段把“网页已经解析成功”与“Agent 可以引用这条事实”之间缺失的门禁补齐。

此前后端已经能解析网页、保存带定位的 `SourceFragment`，也提供单片段手工晋级接口；但前端
仍需自行填写产品、Claim 类型和四个质量分数，无法保证这些元数据与竞品资料血缘及已确认
Source Routing 一致。本 Pipeline 提供项目级 Evidence Draft 批次，并保存一次性人工决定。

```text
ready Source Asset
→ succeeded Collection Job
→ persisted Parsed Artifact
→ verified Source Fragment + exact Source Locator
→ confirmed Source Routing
→ product / dimension lineage
→ deterministic Evidence Draft
→ human selects allowed Claim type
→ provenance is verified again
→ partially_verified Evidence with Evidence ID
→ Source Requirements reevaluation
```

创建批次时后端不会调用模型或创建 Evidence。每个 Draft 会展示：

- 原始片段及 Source Locator；
- `eligible`、`blocked` 或 `already_promoted`；
- 已确认路由和允许的 Claim 类型；
- 从竞品资料发现/接入血缘读取的准确产品、角色和维度；
- 固定策略生成的质量先验和原因；
- 阻止晋级的具体原因。

产品、地区、Source Locator 和四个质量先验不能由客户端覆盖。人工只选择 Draft、允许的
Claim 类型、可选发布时间和用户分群。官方产品资料不能被选择为 `user_opinion`；竞品资料
缺少或存在多个产品血缘时保持 blocked。

质量字段用于 Evidence 检索排序，不代表事实已经得到多源证实：

- `confidence` 表示片段提取/定位可靠度；
- `authority_score` 来自已确认资料路由；
- `recency_score` 按已审核发布时间的固定区间计算，未知时为中性值；
- `diversity_score` 根据项目内同域名 Evidence 数量计算。

晋级时仍会重新校验 Source Asset、Collection Job、Parsed Artifact、内容 Hash、Excerpt Hash、
媒体衍生物 Hash 和 Locator。通过也只进入 `partially_verified`，因为“引用与原文一致”不等于
“来源主张已经被独立证实”。相同原文若已经使用不同证据元数据入湖，会明确返回冲突。

接口：

```text
POST /api/v1/projects/{project_id}/fragment-evidence-batches
GET  /api/v1/projects/{project_id}/fragment-evidence-batches
GET  /api/v1/projects/{project_id}/fragment-evidence-batches/{batch_id}
POST /api/v1/projects/{project_id}/fragment-evidence-batches/{batch_id}/decision
```

同一 Gate 决定重复提交时幂等返回；不同决定返回冲突。晋级中断后，相同请求会跳过成功项并
重试失败项。每项结果保存 Evidence ID 或错误码，批次最终为 `completed` 或 `partial`。
单批最多处理 200 个 Fragment；大页面必须先通过 Fragment 列表选择明确 ID，后端不会静默
截断或自动让模型挑选片段。

测试映射：

- `tests/unit/test_fragment_evidence_contracts.py`
- `tests/integration/test_fragment_evidence_pipeline_api.py`
- `scripts/smoke_fragment_evidence_pipeline_live.py`
