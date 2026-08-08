# 统一资料路由与前端联调说明

## 目标

资料路由位于统一资料中心和 Evidence Lake 之间，解决“用户只提交一次资料，多个 Agent
如何得到适合自己的输入”。它不会创建产品事实，也不会替代 Evidence 审核。

```text
授权网页/文件/媒体
→ Source Processing
→ 确定性路由规则
→ 必要时调用项目所选模型补充多标签分类
→ 高置信规则/规则模型一致时自动确认，其他情况等待人工决定
→ 已确认 route 供领域 Evidence Context 查询
→ Source Fragment 仍需独立审核后才能晋级 Evidence
```

同一资料可以拥有多个 route，例如官方商品页可以同时属于 `official_product`、
`price_channel` 和 `technical_document`。路由和 Claim 类型分开保存：route 决定交给哪个
Agent，Claim 类型限制该 Agent 可以从片段中审核出哪类事实。

## 分类边界

确定性规则只读取来源域名、URL 路径、文件/媒体类型、授权元数据、用户填写的宽泛用途和
有界 Source Fragment。规则能够识别零售域名、商品路径、币种/价格、库存、促销、评价、
技术词和企业内部授权等可解释信号。

只有规则没有覆盖或存在低置信建议时才调用 Model Gateway。模型：

- 只能返回固定 route 和 Claim 类型枚举；
- 不得提取价格、规格、用户结论或未来机会；
- 不得访问互联网或使用训练知识补全资料；
- 每次调用保存 Agent Run、Model Call、模型和 Prompt 版本审计；
- 失败时保留失败审计并回退确定性建议，不生成假分类。

自动确认只适用于所有建议均达到阈值，且建议来自确定性规则或规则与模型的一致结果。
模型单独建议、规则冲突和低置信分类保持 `needs_review`。人工可以确认、修改或全部拒绝，
但每个 route 只能选择其白名单内的 Claim 类型。

## 公共 API

```http
GET  /api/v1/projects/{project_id}/sources/{source_asset_id}/routing
POST /api/v1/projects/{project_id}/sources/{source_asset_id}/routing/analyze
POST /api/v1/projects/{project_id}/sources/{source_asset_id}/routing/decision
```

分析请求：

```json
{
  "use_model": true,
  "force": false
}
```

人工确认示例：

```json
{
  "action": "confirm",
  "selections": [
    {
      "route": "official_product",
      "claim_types": ["vendor_claim", "specification"]
    },
    {
      "route": "price_channel",
      "claim_types": ["price_observation", "channel_availability"]
    }
  ],
  "actor": "research-lead",
  "reason": "确认该资料同时用于官方产品和价格渠道研究。"
}
```

前端资料中心应展示建议 route、分类置信度、可解释信号、分类来源、确认状态和模型审计，
默认隐藏内部 Claim 类型细节。用户选择“自动识别”即可，不需要理解 Agent 内部结构。

## 当前 Agent 接线

官方产品 Evidence Context 已严格读取 `status=confirmed` 且包含 `official_product` route 的
资料。未分析、待审核或被拒绝资料即使已经存在 Evidence，也不会进入官方产品专家。
价格渠道、用户评价及后续 Agent 应复用 `SourceRoutingRepository.confirmed_source_asset_ids`
建立各自的最小 Evidence Context，不再新建上传入口。

## 事件与持久化

路由记录保存在 `source_routings`，每个项目内的一份 Source Asset 只有一个当前路由记录，
重新分析保持稳定 ID 并更新输入 Hash。项目 SSE 会收到：

```text
source_routing_analyzed
source_routing_decided
```

事件只包含状态、数量、确认 route 和 actor 等安全字段，不包含 Prompt、原始响应或 API Key。

## 验证

- `tests/unit/test_source_routing_contracts.py`：枚举、重复项和 route/Claim 白名单；
- `tests/unit/test_source_routing_rules.py`：零售、官方、技术、多标签和未知资料；
- `tests/integration/test_source_routing_api.py`：网页解析、规则、真实 Model Gateway 契约、
  幂等、人工决定、事件和“不创建 Evidence”边界；
- `tests/integration/test_official_product_agent.py`：未确认资料不能进入官方专家；
- `scripts/smoke_source_routing_live.py`：授权真实网页分别调用 GLM 5.2 与 DeepSeek V4 Pro。

本分支没有新增爬虫，也没有提交模型密钥、真实网页快照、Evidence 或运行 Trace。
