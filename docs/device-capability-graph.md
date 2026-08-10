# 设备能力图（Device Capability Graph）

> 分支：`evidence/device-capability-graph`
>
> 状态：公共 API、领域契约、持久化、确定性查询和测试已实现；不包含策略生成或企业设备 API。

## 1. 为什么必须先做能力图

生态机会 Agent 可以提出“门口视觉设备 + HomeBase 本地计算 + 家庭状态信号”的跨设备方案，但不能仅凭模型常识
断言某个 eufy 型号一定具备对应能力。设备能力图把两个问题分开：

1. 厂商设备在合格 Evidence 中被证明具备什么能力；
2. 用户授权填写的家庭设备清单中，哪些真实设备实例可以提供这些能力。

后续 Agent 只消费能力图的结构化查询结果。缺资料时必须得到 `unknown` 或 `unavailable`，不能让 Prompt 补齐。

## 2. 数据边界

### 2.1 厂商通用目录

`CatalogDevice` 保存项目内研究过的设备型号，包括：

- 厂商、产品名、型号、品类和生命周期；
- 设备身份 Evidence；
- Sensor、Action、Compute、Storage、Connectivity、Context 六类能力断言；
- 每条能力断言的支持/不支持/未知、可用性、置信度、最大延迟、数据处理位置、授权要求、离线支持和 fallback；
- 精确 Capability Claim ID 与 Evidence IDs。

设备身份和所有能力断言必须引用当前项目 `verified` 或 `partially_verified` Evidence。其他项目 Evidence 与
`unverified/outdated/mock/invalid` Evidence 会被拒绝。

同一能力允许保存相互冲突的断言。例如官方产品页声称支持某能力，而限制说明明确否定特定条件下的支持，两个断言
都会保存；查询返回 `conflict`，不会用最后一次写入覆盖。

### 2.2 用户家庭快照

`HouseholdSnapshot` 是用户明确授权的家庭设备清单版本。它只保存：

- 粗粒度位置，例如 front door、garage；
- 设备显示名、品类和可选目录映射；
- online/offline/unknown；
- authorized/denied/unknown；
- 跨设备连接、事件、控制或上下文关系。

接口不提供精确地址、序列号、原始家庭视频、生物识别数据字段。每次更新生成新版本，旧版本变为
`superseded`，保证审计时可以解释当时依据的是哪份家庭状态。

确认过的设备关系必须引用 Evidence；仅由用户说明的关系标记为 `user_declared`，不能冒充厂商事实。

## 3. 当前真实 `/api/v1` 接口

```text
POST   /projects/{project_id}/device-capabilities/catalog
GET    /projects/{project_id}/device-capabilities/catalog
GET    /projects/{project_id}/device-capabilities/catalog/{catalog_device_id}
PUT    /projects/{project_id}/device-capabilities/catalog/{catalog_device_id}
DELETE /projects/{project_id}/device-capabilities/catalog/{catalog_device_id}

PUT    /projects/{project_id}/device-capabilities/household-snapshot
GET    /projects/{project_id}/device-capabilities/household-snapshot

POST   /projects/{project_id}/device-capabilities/queries
```

删除仍被任一历史家庭快照引用的目录设备会返回 `DEVICE_CATALOG_IN_USE`，不会级联删除快照。

## 4. 确定性查询规则

查询输入是一个或多个 `capability_key`，可以限定位置和能力类型。每项返回：

- `available`：至少一个匹配设备有合格支持 Evidence，运行状态和授权允许；
- `unavailable`：设备明确不支持、能力不可用、授权被拒绝，或离线且没有离线支持；
- `unknown`：设备未映射目录、没有该能力断言、在线/授权/离线支持未知；
- `conflict`：支持与不支持 Evidence 同时存在，或合格 Evidence 对可用性给出相反结论。

同一需求存在多个设备时按“conflict → available → unknown → unavailable”聚合，因为任何事实冲突都必须先处理，
而任一可靠设备可满足需求即可覆盖其他明确不支持的不同设备。多个需求组成一个方案时按 AND 关系聚合：任一
`unavailable` 表示当前方案不能完整运行；任一 `unknown` 表示尚不能证明；任一 `conflict` 要求先解决冲突。

查询时会重新检查目录身份与能力 Evidence 的当前状态。Evidence 后续变成 outdated/invalid 或被移除后，历史能力断言
不再产生 `available`，而是返回 `CAPABILITY_EVIDENCE_STALE` / `DEVICE_IDENTITY_EVIDENCE_STALE` 与 `unknown`。

查询结果返回：

- 使用的家庭快照 ID 和版本；
- 每个需求的匹配家庭设备、目录设备和 Capability Claim IDs；
- 精确 Evidence IDs；
- 稳定问题码，例如 `UNMAPPED_HOUSEHOLD_DEVICE`、`CAPABILITY_NOT_DECLARED`、
  `DEVICE_OFFLINE_NO_FALLBACK` 和 `CONFLICTING_CAPABILITY_EVIDENCE`。

## 5. 数据库与迁移

Alembic 头：`0019_device_capability_graph`。

新增表：

- `device_catalog`；
- `device_capability_claims`；
- `household_device_snapshots`；
- `household_devices`；
- `household_device_relations`。

迁移测试使用注入的内存数据库真实执行从空库到 `head`，再降级到 `0018_universal_agent_recovery`，不会写入
项目运行数据库。

## 6. 明确不包含

- 不调用大模型抽取或生成能力；
- 不自动生成生态机会或安全策略；
- 不接入、模拟或伪造 eufy 企业内部 API；
- 不读取或保存家庭实时视频；
- 不把用户声明当成厂商官方事实；
- 不跨项目复用 Evidence 或家庭快照。

未来获得企业授权后，可以增加 Device API Adapter，把经过权限和审计校验的真实设备状态写入同一快照契约；
没有 Adapter 时必须明确 `unavailable`，公共查询契约无需改变。

## 7. 自动化验证

```text
tests/unit/test_device_capability_contracts.py
tests/unit/test_device_capability_query.py
tests/integration/test_device_capability_api.py
tests/integration/test_device_capability_migration.py
```

下一分支：`agent/ecosystem-opportunity`。它消费用户研究、竞品综合、共享 Evidence 和本能力图，动态生成目标 3 个、
最多 5 个生态候选；本分支本身不生成任何未来产品结论。
