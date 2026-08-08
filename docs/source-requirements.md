# 资料范围与准备度前后端联调说明

## 目标

资料准备度位于 Research Brief、统一资料中心和领域 Agent 之间，负责回答三个问题：

1. 本次研究究竟要比较哪些准确产品；
2. 每个研究维度需要哪些资料；
3. 当前资料是否已经形成可以交给 Agent 的 Evidence。

它不负责搜索竞品、抓取网页、解析文件、创建 Evidence 或生成研究结论，也不会调用模型。

```text
Brief
→ 用户确认目标产品、竞品和研究维度
→ Source Requirements 实时读取 Source、Routing、Collection Job 和 Evidence
→ blocked：产品范围不完整
→ partial：范围完整，但资料或审核未完成
→ ready：最小 Evidence 要求全部满足
```

## 公共 API

```http
GET /api/v1/projects/{project_id}/source-requirements
PUT /api/v1/projects/{project_id}/source-requirements/scope
```

保存范围示例：

```json
{
  "target_products": [
    {"brand": "eufy", "model": "E340", "variant": null}
  ],
  "competitors": [
    {"brand": "Ring", "model": "D200", "variant": null}
  ],
  "dimensions": ["official_product", "price_channel", "user_review"],
  "actor": "research-lead",
  "reason": "确认目标产品、首轮竞品和完整竞品研究维度。"
}
```

允许先保存 `model=null` 的候选，便于下一分支接入自动竞品发现；但准确型号补齐前整体状态
保持 `blocked`。范围更新保存在 `source_requirement_scopes`，同时发送
`source_requirement_scope_updated` 项目事件。事件只包含数量、维度和 actor，不包含原始
资料、Evidence 摘要或凭据。

## 确定性满足规则

每一项资料要求区分：

- `detected_source_asset_ids`：根据用户填写的资料名称、用途和 URL 找到的相关资料；
- `matched_source_asset_ids`：已经存在合格 Evidence 的资料；
- `matched_evidence_ids`：真正满足要求、可以交给 Agent 的证据。

一份 Source Asset 只有同时满足以下条件才能让资料要求变为 `satisfied`：

1. 资料状态为 `ready`，且属于当前项目；
2. route 已确认并符合研究维度；
3. Source Fragment 已通过现有受控服务晋级为 Evidence；
4. Evidence 状态为 `verified` 或 `partially_verified`；
5. Claim 类型符合该 route 白名单；
6. Evidence 的 `product` 与确认的品牌、型号和版本精确对应；
7. 价格 Evidence 的 `region` 与 Brief 的目标地区一致。

因此“上传了一个文件”“页面已经解析”或“模型知道该产品”都不能单独满足资料要求。

## 前端状态与动作

- `blocked`：没有目标产品、没有竞品或缺少准确型号；不得启动完整竞品研究；
- `partial`：产品范围完整，但某些资料缺失、处理失败、route 未确认、Evidence 未审核或地区不符；
- `ready`：用户选择的所有研究维度均具有最小合格 Evidence。

前端应优先展示 `missing_actions`，并允许用户：

- 补充或替换链接/文件；
- 进入现有资料处理、路由和 Evidence 审核页面；
- 修改产品范围；
- 后续进入 Competitor Discovery Agent 自动发现并确认竞品。

`unassigned_source_asset_ids` 表示已经确认到相关研究 route、但尚未形成当前产品和地区可用
Evidence 的资料，适合在资料中心显示“待关联/待审核”。

## 当前边界

- 本分支不会自动发现 Ring、Nest 或 Arlo 等竞品；
- 不新增搜索 API、爬虫或外部 Runtime 调用；
- 不使用测试数据填充生产结果；
- 不把 Source Asset、搜索摘要或大模型知识当成 Evidence；
- 已实现的 `evidence/search-discovery-connector` 可消费该范围与缺口并返回候选 URL，但本
  模块不会自动触发联网请求；下一步由 `agent/competitor-discovery` 对候选竞品进行判断和
  人工 Gate。

## 自动化验证

- `tests/unit/test_source_requirement_contracts.py`：范围去重、目标/竞品冲突、维度和型号约束；
- `tests/integration/test_source_requirements_api.py`：无范围阻断、缺型号阻断、范围审计、资料
  处理失败、route/Evidence 门禁、产品关联、地区隔离、输入 Hash 更新和完整就绪。
