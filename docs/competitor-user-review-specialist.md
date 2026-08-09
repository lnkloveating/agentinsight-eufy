# 竞品用户评价专家

## 职责边界

`Competitor User Review Specialist` 是竞品主管的第三个 A2A 专家。它只解释已经授权、解析、
审核并进入 Evidence Lake 的真实用户表达，不负责发现竞品、搜索、抓取或把网页内容自动
认定为评论。

```text
授权评论页/研究文件
→ Source Fragment
→ 确认 user_review 路由
→ 人工审核为 user_opinion Evidence
→ UserReviewEvidenceContextBuilder
→ A2A User Review Specialist
→ Model Gateway
→ 确定性引用、产品与重复主题门禁
→ CompetitorSpecialistArtifact
```

同一资料必须先经过统一 Source Ingestion。用户评价专家只读取当前项目、已确认
`user_review` route、状态为 `verified/partially_verified`、Claim 类型为 `user_opinion` 且
产品血缘与主管请求完全一致的 Evidence。它不能读取价格、官方声明或候选搜索摘要。

## 输出语义

- `review_themes`：产品、主题名称、正/负/混合情感、用户表达、触发事件、用户影响与引用；
- `recurrence_status`：由后端根据 Evidence 和独立来源数计算为 `single_report` 或
  `repeated_across_sources`，不由模型声明；
- `contradictions`：同时保留相反用户观点及其 Evidence IDs；
- `sample_limitations`：明确地区、用户分群、来源数量和代表性限制；
- `research_gaps`：证据不足时的可执行补研问题；
- `evidence_coverage`：请求产品、已覆盖产品、独立来源、单条与重复主题数量及 Context Hash。

“评论中没有提到”只能形成未知项，不能推断用户没有某个痛点。单个页面、单个作者或重复转载
不能被包装成“普遍需求”。后端只把至少两条 Evidence 且来自至少两个独立来源的主题标为
重复主题；其他主题仍可展示，但不会让专家状态晋级为 `completed`。

## 主流程与前端

生产启动将 `user_review` 专家绑定到真实 Model Gateway。至此竞品主管的官方产品、价格渠道
和用户评价三条专家泳道都有真实 Adapter；但父级 `completed` 仍取决于各泳道自己的证据
覆盖，不能因为“都已绑定”就强制通过。

本分支不新增公共 HTTP API，因此 `docs/api/openapi.yaml` 不变。前端继续通过 Agent Run、
A2A Task 审计和 SSE 事件展示运行状态；完整竞品优缺点矩阵与未来机会预测仍属于后续竞品
综合分支。

## 验证

- 单元测试覆盖 Schema、引用越界、错产品、Claim 类型、重复主题与状态门禁；
- 集成测试覆盖授权评论资料、路由、Evidence Context、Model Gateway、A2A 持久化与父级聚合；
- `scripts/smoke_competitor_user_review_live.py` 使用本地 `.env`、临时数据库和经人工审核的
  真实评论片段完成模型冒烟，不输出密钥、评论原文或运行 Trace。

2026-08-09 使用公开 E340 第一人称实测页完成真实验证：网页由确定性 HTML Parser 解析为
377 个片段，审核晋级 1 条 `user_opinion` Evidence。GLM 5.2 首次结构化输出失败后由 Model
Gateway 自动重试成功，生成 4 个 `single_report` 主题和 3 个样本限制；DeepSeek V4 Pro
一次调用完成，生成 2 个 `single_report` 主题和 1 个样本限制。两者都按门禁保持 `partial`，
因为单一来源不能证明跨来源重复，这属于正确结果而不是调用失败。
