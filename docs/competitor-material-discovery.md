# 竞品研究资料发现

本阶段解决“已经确认准确竞品后，到哪里找可研究资料”的问题。系统不让业务 Agent
自由猜网址，也不把搜索摘要当成事实；它从项目当前 `Source Requirements Scope` 读取准确
产品与研究维度，生成确定性搜索计划，再调用已注册的真实 Search Provider。

每个产品最多产生三类独立搜索运行：

- `official_product`：官方产品页、规格、兼容性和说明书候选；
- `price_channel`：目标地区价格、库存、授权零售和渠道候选；
- `user_review`：用户评价、长期体验和问题反馈候选。

完整边界如下：

```text
准确目标产品/竞品 + 已确认研究维度
→ 确定性查询计划
→ 真实 Search Discovery Run
→ candidate_only 候选
→ 用户选择候选并确认公开资料授权
→ Source Asset + Collection Job + 产品/维度血缘
→ 现有网页处理与 Source Routing
→ Source Requirements 重新评估
→ 后续 Source Fragment / Evidence 分支
```

发现阶段不会访问候选正文、调用业务模型、创建 Source Asset、Source Fragment、Evidence、
Claim 或竞品结论。只有人工 `confirm` 后选中的当前批次 candidate ID 才能进入资料处理链路；
跨批次 ID、范围外产品、缺少准确型号和未确认授权都会被拒绝。

前端可使用以下接口构建统一的“资料发现”页面：

```text
POST /api/v1/projects/{project_id}/competitor-material-discoveries
GET  /api/v1/projects/{project_id}/competitor-material-discoveries
GET  /api/v1/projects/{project_id}/competitor-material-discoveries/{material_discovery_id}
POST /api/v1/projects/{project_id}/competitor-material-discoveries/{material_discovery_id}/decision
```

创建请求中的 `products` 和 `dimensions` 为空时，后端使用当前范围内全部具有准确型号的产品
和全部已确认维度；前端也可以只选择一部分以控制搜索调用量。响应中的每个 item 都保留准确
产品、角色、维度、查询和真实 `SearchDiscoveryRun`，便于展示执行状态与候选来源。

人工确认是一次性 Gate。完全相同的重复请求幂等返回原决定；不同决定返回冲突。候选 URL
会再次执行公开 URL 规范化和域名一致性检查，同一项目中的重复链接复用已有 Source Asset。
后台网页处理失败只会记录对应 Collection Job 的明确状态，不会把不可访问内容交给模型猜测。

测试映射：

- `tests/unit/test_competitor_material_discovery_contracts.py`
- `tests/integration/test_competitor_material_discovery_api.py`
- `scripts/smoke_competitor_material_discovery_live.py`
