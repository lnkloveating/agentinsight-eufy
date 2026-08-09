# 竞品价格渠道专家

## 职责与数据边界

`Price Channel Specialist` 负责把已经审核进入 Evidence Lake 的价格、库存、卖家和促销片段
转换成可比较的结构化观察。它不负责搜索、抓取或授权资料；这些步骤仍由 Material
Discovery、Source Onboarding、Web Connector、Source Processing 和 Fragment Evidence
Pipeline 完成。

```text
授权价格/零售网页
→ 已验证 Source Fragment
→ 人工确认 price_channel 路由与 Claim 类型
→ Evidence Lake
→ PriceChannelEvidenceContextBuilder
→ A2A Price Channel Specialist
→ Model Gateway
→ 确定性引用、产品、地区和时间门禁
→ CompetitorSpecialistArtifact
```

专家只消费 `price_observation`、`channel_availability`、`seller_information` 和 `promotion`
Evidence，并要求 Evidence 地区与主管请求一致。每条输出必须使用主管给定的产品标签并引用
本次上下文中的 Evidence ID。模型负责理解原文中的价格语义，后端负责验证范围、引用、
Claim 类型，并从 Evidence 采集时间生成观察时间范围。

## 价格语义

- `regular`、`sale`、`member`、`bundle` 和 `from` 价格分别保存；
- 金额使用十进制定点字符串与 ISO 4217 大写币种，避免浮点误差；
- 渠道、卖家、地区、产品变体和促销条件均显式保存；
- `listed` 只表示存在商品页，不等于有货；
- 网页被采集时的价格只是一条时间化观察，不代表永久价格或全网最低价；
- 证据没有说明的内容写入未知项或补研缺口，不能由模型补齐。

## 接入状态

生产启动将 `price_channel` 注册为竞品主管的真实 A2A 专家，与官方产品专家并行执行。用户
评价专家仍未绑定，因此在该专家完成后，父级竞品 Artifact 仍可能为 `partial`。本分支不
新增公共 HTTP API，`docs/api/openapi.yaml` 保持不变；运行状态继续通过既有 Agent Run、
A2A Task 审计和 SSE 事件表达。

## 验证

- 单元测试覆盖 Schema、Evidence 越界、产品/地区错配、时间血缘和状态计算；
- 集成测试覆盖路由确认、Evidence Context、真实 Model Gateway 契约、A2A 持久化与父级聚合；
- `scripts/smoke_price_channel_live.py` 使用本地 `.env`、临时数据库和授权网页进行可重复真实
  模型冒烟，不输出密钥，也不保存生成 Evidence 或 Runtime Trace。
