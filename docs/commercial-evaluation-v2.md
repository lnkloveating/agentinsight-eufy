# Commercial Evaluation v2：后端与前端接入说明

## 作用和边界

Commercial Evaluation v2 在生态机会通过技术可行性、策略编译和 dry-run 验证后，判断它是否
值得进入下一轮用户与商业试点验证。它不会计算商业加权总分，也不会宣称产品已经可以上架或保证收益。

三项结论彼此独立：

1. `user_value`：真实用户资料是否支持该问题和值得改善；
2. `business_model`：市场、价格、渠道或企业资料是否支持继续验证商业假设；
3. `delivery_operations`：直接继承 Technical Feasibility 和 Policy Verification 的既有结论，
   商业模型不能重新猜测设备或技术能力。

模型负责整理用户价值、商业事实和待验证假设；后端负责 Evidence 边界、维度状态、交付结论、
补研要求和最终 recommendation。

## API

- `POST /api/v1/projects/{project_id}/agents/commercial-evaluation-v2`
  - `opportunity_ids` 可省略，省略时使用最新技术评估中的已选生态机会；
  - 只能选择已完成技术评估的 1–5 个机会；
  - 策略验证为 `failed` 或 `inconclusive` 时拒绝运行。
- `GET /api/v1/projects/{project_id}/agents/commercial-evaluation-v2/artifacts`
  - 按版本返回历史 Artifact。

## Evidence 规则

- 用户价值 Claim 只能引用最新 User Research Artifact 已使用的 Evidence ID；
- 商业 Claim 只能引用 `fact`、`market_fact`、价格、渠道、卖家或促销类受控 Evidence；
- Technical Feasibility 与 Policy Verification Evidence 只用于确定性交付结论；
- 越界 Evidence ID、模型自报 recommendation、delivery 或 weighted score 会被拒绝；
- 模拟数据、模型常识和公开资料不能证明真实销量、成本、退货率、支持成本或付费转化。

## Recommendation

- `recommend_for_validation`：三项结论受支持，只表示可以继续做受控验证；
- `conditional`：存在明确技术、运营或商业前置条件；
- `needs_more_evidence`：证据不足，必须给出结构化 `commercial_gaps`；
- `do_not_recommend`：至少一个核心维度有证据支持的否定结论。

当结果为 `needs_more_evidence` 时，LangGraph 进入通用 Source Recovery。前端显示补研弹窗，用户可
填写企业内部区间数据、上传文件/PDF，或绑定已经处理完成的 Evidence。补充完成后只重跑 Commercial
Evaluation，不重复用户研究、竞品研究、技术评估和策略验证；达到最大补研次数仍不足则返回
`inconclusive`。

## 前端展示

“商业验证”页建议展示：

- 顶部 recommendation 标签和“仅决定是否继续验证，不代表上架或收益保证”提示；
- 用户价值、商业模式、交付运营三张独立结论卡；
- 每条 Claim 的 Evidence ID、来源与原文下钻；
- 可验证的商业假设、验证方法和决策指标；
- 技术 Artifact、策略验证 Artifact、前置条件和失败场景链接；
- 缺证时复用全局补研弹窗，不展示虚构的百分制商业评分。

主路径完成后停在 `awaiting_red_team_review`，下一分支由红队和用户质疑决定维持、降级、返工或淘汰。
