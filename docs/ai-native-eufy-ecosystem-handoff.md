# eufy 生态 AI 原生方向：后端开发交接与改造计划

> 状态说明：本文保留 2026-08-10 产品方向变更时的历史现场，文中的旧 `agent/commercial-evaluation`
> 分支状态已经失效。当前实时开发状态、测试结果和下一步统一以 `docs/CODEX_HANDOFF.md` 为准。

> 交接日期：2026-08-10
>
> 仓库：`agentinsight-eufy`
>
> 远程 `main` 基线：`0f611f1 合并通用智能体资料补研流程`
>
> 历史工作分支：`agent/commercial-evaluation`（已删除，不应恢复合并）
>
> 历史分支提交：`942d491 定义商业评估智能体接口契约`

## 0. 给接手开发者的最短说明

本项目原本的主路径是：

```text
调研智能家居行业与 eufy 产品
→ 用户研究与竞品研究
→ 生成 3～5 个未来“产品”候选
→ 技术、商业、红队评估
→ 选择门铃包裹风险场景做 Demo
```

现在产品方向已经调整为：

```text
调研 eufy 家庭安防生态
→ 发现尚未满足的家庭安全目标
→ 生成 3～5 个生态级解决方案候选
→ 选择“可验证家庭安全策略 Agent”
→ 读取家庭设备与能力
→ 把自然语言安全目标编译成跨设备策略
→ 在上线前完成盲区检查、场景模拟、红队验证和失败返工
→ 用户批准后才允许部署
→ 使用包裹保护作为第一个端到端验证切片
```

最终创新不是“再做一套多 Agent 调研系统”，也不是“再做一个能检测包裹的门铃”。最终产品命题是：

> **eufy Guardian Agent：把用户的家庭安全目标转换成可解释、可验证、可审批、可部署的跨设备安全策略。**

研究多 Agent 系统是“发现和验证未来产品的方法”，不是参赛作品唯一的创新点。包裹场景是验证生态能力的第一个切片，不是提前写死的研究结论。

---

## 1. 重要的产品边界

### 1.1 不要使用的宣传表述

以下表述没有证据支撑，后续报告、Prompt 和前端文案不得直接使用：

- “全球第一个智能家居生态 Agent”；
- “目前没有任何厂商在做生态 AI”；
- “竞品只能检测和通知”；
- “这套方案一定可以上线”；
- “模拟测试通过就证明真实世界安全”；
- “Anker 内部没有类似系统”。

公开资料已经显示，eufy、Google 等厂商正在布局本地 AI Agent、视频理解、自然语言自动化和跨设备控制。因此，“生态 AI Agent”本身不是足够精确的创新边界。

### 1.2 可以验证的差异化命题

本项目应当验证下面这个更窄、更可落地的命题：

> 主流智能家居 AI 已经能够理解、搜索、控制和生成自动化；但“安全目标如何变成经过证据审计、盲区识别、对抗测试和失败返工的可部署策略”仍可能存在产品机会。

这仍然只是待验证假设。Competitor Agent 必须使用 Evidence 验证以下维度：

1. 是否支持自然语言创建自动化；
2. 是否支持跨摄像头或跨传感器理解；
3. 是否能够从抽象安全目标自动生成策略；
4. 是否在部署前自动生成正常、异常和对抗场景；
5. 是否计算覆盖盲区和不可观测状态；
6. 是否区分历史真实事件、用户上传事件与模拟事件；
7. 是否能够根据失败测试自动修改策略；
8. 是否提供动作权限、人工批准、降级和回滚；
9. 是否可以主要在本地设备或 HomeBase 上执行；
10. 是否公开提供策略验证结果或安全覆盖说明。

如果竞品证据证明已经完整覆盖上述闭环，系统必须降低差异化判断、要求重新定义候选，不能强行宣布创新。

### 1.3 AI 原生判定标准

一个候选只有同时满足下列条件，才可以标记为 `ai_native_qualified`：

- 用户输入的是开放式安全目标，而不是固定功能开关；
- 系统需要理解家庭、设备、空间、习惯或事件上下文；
- 系统会动态生成跨设备策略，而不是套用固定模板；
- 系统能够识别当前缺少哪些信息或设备能力；
- 系统能够动态生成验证场景并根据失败返工；
- 模型推理与确定性安全校验明确分离；
- 敏感动作必须经过权限策略或 Human Gate；
- 不可观测、低置信度或设备离线时具有明确降级方案；
- 去掉 AI 后，产品的核心“目标理解、策略生成、补证与返工”能力无法成立。

仅仅使用大模型生成通知文案、总结录像、搜索视频或生成一条普通自动化，不能单独通过 AI Native Gate。

---

## 2. 新方向的完整用户故事

### 2.1 研究阶段

用户创建研究项目时可以输入：

```text
研究 eufy 家庭安防生态未来两到三年的 AI 原生产品机会。
重点关注普通家庭难以配置、难以判断和难以验证的安全问题。
```

系统执行：

```text
Research Brief 确认
→ 用户研究
→ 竞品发现与竞品三专家研究
→ Evidence 审计
→ 生成多个生态级机会
→ AI Native Gate
→ 技术与设备能力可行性
→ 商业判断
→ 红队质疑与定向返工
→ 人工选择一个生态方案进入验证
```

### 2.2 产品使用阶段

用户对 Guardian Agent 输入：

```text
工作日家里没人时保护门口包裹。
家人取件不要提醒；陌生人接近、包裹长时间未取或天气风险上升时提醒我。
```

系统执行：

```text
读取已授权的家庭设备清单
→ 建立设备—传感器—能力—空间关系图
→ 判断哪些状态可观测、哪些存在盲区
→ 生成跨设备安全策略草案
→ 生成正常、异常、边界和对抗测试场景
→ 用历史事件、用户授权素材或明确标注的模拟事件测试
→ 输出通过、失败、证据不足和风险项
→ 失败时修改策略、降级或请求补充信息
→ 用户批准
→ 才允许生成部署指令
→ 运行后根据误报、漏报和用户反馈迭代
```

### 2.3 包裹场景中的策略示例

```text
基础事件：包裹送达
事件状态：包裹仍在门口
上下文：用户不在家
上下文：陌生人接近或天气风险上升
推理：包裹无人照看且风险增加
动作：先通知用户；涉及报警、开锁或联系第三方时请求批准
降级：身份、路径或包裹状态不可确认时，输出“证据不足”，不能宣称被盗
```

动态验证场景示例：

- 家人正常取件；
- 快递员二次靠近；
- 陌生人拿走包裹；
- 两个包裹互相遮挡；
- 鞋盒、花盆被误识别为包裹；
- 夜间低照度；
- 门铃断网或电量不足；
- 用户在家状态不可用；
- 天气接口超时；
- 人员身份冲突；
- 门磁显示从室内开门，但视觉身份未知。

测试场景数量不得固定为三个。Agent 根据策略中的状态、设备能力、失败模式和用户提供的资料动态生成；后端只设置最小覆盖类型和数量上限。

---

## 3. 当前代码真实进度

### 3.1 已经合并到 `main`，可以继续复用

以下能力已经在 `main@0f611f1`，新方向不应重写：

#### 项目、运行与编排底座

- 项目生命周期、Research Brief 和人工审批；
- SSE 项目事件；
- LangGraph 共享状态、Checkpoint、三个 Human Gate 和定向重跑；
- Agent Runtime Gateway、版本化 Artifact Store、超时、取消和错误分类；
- 内部模型 Adapter、外部 CLI Adapter 和 OpenCode Driver；
- 多模型 Model Gateway、模型选择、Prompt Registry、结构化输出、重试和成本审计。

#### 资料与证据底座

- 用户授权文件和公开 URL 接入；
- 网页安全校验与正文处理；
- PDF、文本、CSV/JSON 等资料处理；
- 媒体容器、音轨、关键帧和衍生产物处理框架；
- Source Routing 和人工确认；
- Evidence、Claim、Collection Job、Claim Gate；
- 项目级共享 Evidence Retrieval；
- Source Requirements；
- Search Discovery/Tavily 候选发现；
- 通用资料不足投影、用户补充内容、Evidence 回流和定向重跑指令。

注意：当前共享检索是可解释的词法与元数据检索，不是向量数据库。当前没有真实 ASR/视觉语义 Connector，不能把“已经抽音轨和抽帧”表述成“已经理解视频”。

#### 已完成的领域 Agent

- User Research Agent；
- Competitor Discovery Agent；
- Competitor A2A Supervisor；
- Official Product Specialist；
- Price/Channel Specialist；
- User Review Specialist；
- Competitor Synthesis 与 Evidence Audit；
- 用户研究和竞品研究汇合后的 `ResearchHandoff`；
- Product Technical Opportunity Agent v1；
- Product Technical Source Recovery。

### 3.2 当前 Product Technical Agent 的行为

当前实现位于：

- `src/backend/app/agents/product_technical/`
- `src/backend/app/application/research/product_technical.py`
- `src/backend/app/api/v1/routes/research.py`
- `src/backend/app/workflows/handoff.py`

它会：

1. 读取 User Research Artifact；
2. 读取 Competitor Synthesis Artifact；
3. 构建 `ResearchHandoff`；
4. 从共享 Evidence Retrieval 获得受控上下文；
5. 动态生成目标 3 个、最多 5 个 `ProductOpportunityCandidate`；
6. 要求每个候选同时引用用户与竞品 Evidence；
7. 运行确定性 Event Understanding Gate；
8. 证据不足时生成 `portfolio_gaps`；
9. 通过通用 Source Recovery 接收补充资料并生成下一版 Artifact。

这个模块不是完全无用。它的 Evidence 边界、Context Builder、版本化 Artifact、Gap 和 Validator 都可以复用。但是其输出语义偏向“产品候选”，缺少生态策略、设备图、AI 原生判定和上线前验证结构。

### 3.3 LangGraph 当前主图状态

`src/backend/app/workflows/graph.py` 已经有以下骨架节点：

```text
brief gate
→ research manager
→ user research + competitor research
→ evidence readiness
→ product technical
→ commercial evaluation
→ red team
→ candidate synthesis
→ scenario gate
→ validation
→ final synthesis
→ final gate
```

骨架支持测试 Runtime、Checkpoint 和返工路由，但完整 HTTP 项目生命周期尚未把所有真实业务 Agent 自动串成一次生产运行。Commercial、Red Team、Candidate Synthesis、Validation 和 Final Synthesis 仍缺少完整真实实现。

### 3.4 当前工作分支的特殊状态

当前不是干净的 `main`，而是：

```text
branch: agent/commercial-evaluation
HEAD:   942d491 定义商业评估智能体接口契约
base:   main@0f611f1
```

`942d491` 只修改了 `docs/api/openapi.yaml`，增加了旧方向的商业评估 API 契约。该契约仍围绕 `Product Technical candidate` 评估用户价值、商业可行性和交付准备度。

当前还有以下未跟踪草稿，尚未提交、尚未接线、尚未完成测试：

```text
src/backend/app/agents/commercial_evaluation/adapter.py
src/backend/app/agents/commercial_evaluation/context.py
src/backend/app/agents/commercial_evaluation/contracts.py
src/backend/app/agents/commercial_evaluation/prompt.py
src/backend/app/agents/commercial_evaluation/validation.py
```

交接结论：

- 不得把 Commercial Agent 写成“已完成”；
- 当前分支不应直接合并到 `main`；
- 不要删除未提交草稿，除非负责人明确决定放弃；
- 新开发应优先从 `main@0f611f1` 创建新方向分支；
- 商业草稿中可复用的 Evidence Context、结构化判定和确定性校验思想，等生态机会、技术可行性与验证 Artifact 稳定后再迁移；
- 旧 OpenAPI 契约需要重新设计，不能直接当作新方向最终接口。

---

## 4. 新旧主路径映射

| 旧模块 | 新方向处理 | 原因 |
|---|---|---|
| Research Brief | 保留并扩展 | 研究对象从单个产品改为 eufy 家庭安防生态和安全目标 |
| User Research | 保留 | 继续输出事件链、痛点、需求和 Evidence IDs |
| Competitor A2A | 保留并扩展维度 | 需要比较生态 Agent、自然语言自动化、策略验证与本地执行 |
| ResearchHandoff | 保留并扩展投影 | 增加生态能力缺口和 AI 原生竞品维度 |
| Product Technical v1 | 保留兼容接口，新建 v2 生态机会 Agent | 避免破坏已有 API 和测试；新输出不再局限单设备产品 |
| Event Understanding Gate | 保留为单场景子 Gate | 它仍适合验证包裹等事件链，但不能代替生态与 AI Native Gate |
| Commercial Evaluation | 暂停，等待上游新 Artifact | 商业判断必须消费生态方案、技术可行性和验证成本 |
| Red Team | 后续实现并扩展 | 需要支持系统自动质疑和用户自定义质疑 |
| Scenario Gate | 保留 | 改为选择“生态方案 + 首个验证策略”，而不是只选硬件产品 |
| Validation | 改为 Security Policy Verification | 运行历史/授权/模拟/红队场景并输出可追溯结果 |
| Package Risk Demo | 保留但重新定位 | 作为 Goal-to-Guard 的第一个纵向切片，不是固定研究答案 |
| Final Synthesis | 后续实现 | 输出生态上架建议、条件、证据、风险和补研计划 |

---

## 5. 建议的新领域契约

必须先修改 `docs/api/openapi.yaml`，再实现代码。不要直接把 v1 的 `ProductOpportunityCandidate` 改成不兼容结构。

### 5.1 解决方案层级

建议新增：

```python
class SolutionScope(StrEnum):
    DEVICE_FEATURE = "device_feature"
    DEVICE_PRODUCT = "device_product"
    ECOSYSTEM_SERVICE = "ecosystem_service"
```

当前挑战的 Candidate Gate 至少要求最终晋级项包含一个 `ecosystem_service`。如果研究证据只支持设备级机会，系统应输出证据不足或方向不成立，不能把设备功能伪装成生态方案。

### 5.2 Ecosystem Opportunity Artifact

建议建立独立的新契约，不覆盖旧 `ProductTechnicalArtifact`：

```json
{
  "artifact_type": "ecosystem_opportunity",
  "schema_version": "1.0",
  "payload": {
    "summary": "...",
    "opportunities": [
      {
        "opportunity_id": "eco_goal_to_guard",
        "name": "eufy Guardian Agent",
        "scope_level": "ecosystem_service",
        "target_user": {},
        "problem": {},
        "safety_goal": "...",
        "ecosystem_blueprint": {},
        "ai_native_case": {},
        "technical_hypotheses": [],
        "commercial_hypotheses": [],
        "validation_plan": {},
        "competitor_gap_ids": [],
        "evidence_ids": [],
        "gate_status": "passed|blocked",
        "gate_issues": []
      }
    ],
    "portfolio_gaps": [],
    "coverage": {}
  }
}
```

### 5.3 Ecosystem Blueprint

建议至少包含：

```json
{
  "required_device_roles": [
    "primary_perception",
    "context_sensor",
    "local_reasoning_hub",
    "user_approval_interface"
  ],
  "required_capabilities": [],
  "cross_device_information_flow": [],
  "deployment_target": "homebase|device|cloud|hybrid",
  "privacy_boundary": {},
  "permission_boundary": {},
  "offline_behavior": {},
  "fallback_behavior": {},
  "known_blind_spots": []
}
```

这里保存“需要什么角色和能力”，不能未经证据直接断言某个 eufy 型号一定具备该能力。具体设备能力必须来自 Device Capability Graph 中带 Evidence ID 的事实。

### 5.4 AI Native Case

```json
{
  "open_ended_goal": "...",
  "why_fixed_rules_are_insufficient": "...",
  "model_responsibilities": [],
  "deterministic_responsibilities": [],
  "ai_removal_test": {
    "core_value_survives_without_ai": false,
    "rationale": "...",
    "evidence_ids": []
  },
  "learning_or_revision_loop": [],
  "safety_constraints": []
}
```

后端只负责校验字段完整性、Evidence ID 范围和规则一致性。是否“真的 AI 原生”还需要模型说明、竞品证据、确定性 Gate 和人工审批共同决定。

### 5.5 Device Capability Graph

该图用于回答“这个家庭现有设备能否支撑策略”，不是保存用户原始视频。

```json
{
  "graph_id": "...",
  "project_id": "...",
  "home_profile_id": "...",
  "nodes": [
    {
      "node_id": "device_doorbell_1",
      "node_type": "device",
      "device_type": "video_doorbell",
      "model": "用户授权后填写或 API 返回",
      "location": "front_door",
      "authorization_status": "authorized",
      "evidence_ids": []
    },
    {
      "node_id": "cap_package_presence",
      "node_type": "capability",
      "availability": "available|partial|unknown|unavailable",
      "latency": {},
      "confidence_boundary": {},
      "privacy_boundary": {},
      "evidence_ids": []
    }
  ],
  "edges": [
    {
      "from": "device_doorbell_1",
      "to": "cap_package_presence",
      "relation": "provides"
    }
  ],
  "unknowns": [],
  "conflicts": []
}
```

来源优先级：

```text
企业内部授权设备 API/能力清单
→ 官方产品与支持文档
→ 用户设备清单
→ 用户授权测试结果
→ 明确标记的假设或模拟能力
```

不允许根据产品名字猜测能力，也不允许把竞品能力复制为 eufy 能力。

### 5.6 Security Policy Draft

大模型生成策略意图，确定性 Compiler/Validator 将其转换和校验为受限 DSL。大模型不能直接生成可执行开锁、报警或联系第三方命令。

```json
{
  "policy_id": "policy_package_protection",
  "goal_id": "goal_unattended_package",
  "version": 1,
  "triggers": [],
  "state_variables": [],
  "context_requirements": [],
  "risk_levels": [],
  "decision_rules": [],
  "recommended_actions": [],
  "action_permissions": [],
  "human_approval_rules": [],
  "fallback_rules": [],
  "rollback_plan": {},
  "assumptions": [],
  "evidence_ids": []
}
```

确定性 Validator 至少检查：

- 所有引用设备和能力都存在于授权 Capability Graph；
- 所有状态变量有来源或明确为不可观测；
- 规则不存在循环、永远为真或永远为假的明显错误；
- 敏感动作具有权限和 Human Gate；
- 设备/网络/模型失败时存在降级；
- 事实性能力声明具有 Evidence ID；
- 模拟输入没有被当成真实 Evidence；
- 模型说明与执行 DSL 分离；
- 策略版本和回滚目标存在。

### 5.7 Verification Scenario 与结果

```json
{
  "scenario_id": "scenario_family_pickup",
  "scenario_type": "normal|boundary|failure|adversarial",
  "provenance": "historical|user_uploaded|enterprise_test|simulated",
  "preconditions": [],
  "event_sequence": [],
  "expected_outcome": {},
  "actual_outcome": {},
  "result": "passed|failed|blocked|inconclusive",
  "observability_gaps": [],
  "evidence_ids": [],
  "simulation_artifact_ids": []
}
```

规则：

- `historical/user_uploaded/enterprise_test` 可以在授权和审核后形成 Evidence；
- `simulated` 只能证明逻辑在模拟条件下的行为，不能证明真实市场事实或真实模型准确率；
- 预期结果应来自用户安全目标、确定性规则或人工确认，不能让同一个模型同时出题、作答并自行宣布正确；
- 每个失败结果要创建 RevisionRequest 或 Source Recovery Gap；
- 无法解决的高风险失败必须阻止部署。

---

## 6. 建议的后端分支顺序

下列分支按依赖顺序开发。每个分支应独立更新 OpenAPI、契约、实现、测试和验收文档，不要放进一个超大分支。

### 分支 1：`domain/ecosystem-opportunity-contract`

目标：定义新方向的公共词汇和 API，不调用真实模型。

任务：

- 在 `docs/api/openapi.yaml` 新增 Ecosystem Opportunity API；
- 新增 `SolutionScope`、`EcosystemBlueprint`、`AINativeCase`；
- 新增 `EcosystemOpportunityArtifact`；
- 在 `ResearchAgentType` 增加独立的 `ECOSYSTEM_OPPORTUNITY`，不要静默改变旧类型语义；
- 在 Source Recovery AgentType 中增加新类型；
- 定义 Gap、Coverage 和版本字段；
- 保留旧 Product Technical API，标记为 legacy 或暂不进入新主路径；
- 单元测试所有 Schema 的边界、重复 ID、未知字段和 Evidence ID 规则；
- 在 `docs/acceptance-criteria.md` 记录契约验收。

不包含：Prompt、真实模型、设备图和商业评估。

验收：

```text
设备功能、设备产品、生态服务能够被明确区分
→ 生态候选包含 AI Native Case 和 Ecosystem Blueprint
→ 旧 Product Technical Artifact 仍可解析
→ 新旧 API 不发生响应结构冲突
```

### 分支 2：`evidence/device-capability-graph`

目标：建立带 Evidence 血缘的设备能力图和用户家庭设备快照。

任务：

- 定义 Device、Sensor、Capability、Action、Location 和关系；
- 区分厂商通用能力与用户家庭实例；
- 支持用户授权填写设备清单；
- 支持官方资料 Evidence 绑定能力；
- 支持未来企业内部 API Adapter，但未配置时明确 `unavailable`；
- 记录可用性、延迟、隐私、授权、置信度、离线状态和 fallback；
- 不保存不必要的原始家庭视频；
- 对冲突能力声明输出 conflict，不静默覆盖；
- 新增 CRUD/查询 API、数据库迁移和测试。

不包含：根据目标生成策略。

验收：

```text
用户登记门铃、HomeBase 和门磁
→ 官方/企业 Evidence 绑定设备能力
→ 系统能够回答某个状态是否可观测
→ 缺能力时返回 unknown/unavailable，而不是模型猜测
```

### 分支 3：`agent/research-brief-clarifier-v2`

目标：把模糊输入逐轮澄清为严格的 AI 原生家庭安防生态 Research Brief。

任务：

- 在正式项目创建前保存独立追问会话；
- 使用 Model Gateway 和版本化 Prompt 动态生成问题；
- 模型只提取有用户消息血缘的字段，后端检查缺失项和完整 Schema；
- 不默认原始媒体、家庭事件、外部共享或高影响动作授权；
- 完成后交给用户确认，再调用现有项目创建和 Brief Gate。

验收：

```text
输入“研究 eufy 未来老人安防产品”
→ 不直接生成方案或项目
→ 动态追问生态范围、风险、信号、隐私、干预和交付物
→ 所有字段校验通过后返回 completed_brief
```

### 分支 4：`agent/competitor-ecosystem-analysis`

目标：在现有三个竞品事实专家之上增加生态发现和生态综合。

任务：

- 比较 Ring、Google Nest、Arlo、eufy 等生态，而不是只比较单款门铃；
- 保留官方产品、价格渠道、用户评价专家作为事实和 Evidence 来源；
- 分析跨设备协作、持续状态、跨时间理解、主动补证、不确定性、干预阶梯、
  本地/云分工、隐私授权、离线降级、照护者流程、失败修订和商业模式；
- 所有事实引用 Evidence ID，未发现保持 unknown/gap；
- 把生态能力矩阵和缺口写回 ResearchHandoff。

验收：

```text
具体设备资料进入三个事实专家
→ 生态综合形成可下钻 Evidence 的能力矩阵
→ 资料不足不写成“竞品没有”
→ 生态缺口进入机会 Agent 上游
```

### 分支 5：`agent/ecosystem-opportunity`

目标：把用户研究、竞品研究和能力证据转换成多个生态级机会。

任务：

- 新建 Agent 模块，不直接覆盖 v1 Product Technical；
- 复用 `ResearchHandoff`、Shared Evidence Retrieval、Artifact Store；
- 扩展 Competitor Projection，加入生态 Agent 和策略验证维度；
- Prompt 要求动态生成目标 3 个、最多 5 个解决方案候选；
- 不能固定输出 Guardian Agent 或包裹场景；
- 每个候选同时引用用户与竞品 Evidence；
- 每个事实性能力假设引用 Evidence 或明确标记 hypothesis；
- 输出 Evidence 不足的 `portfolio_gaps`；
- 注册 Internal Model Adapter 和 Prompt；
- 新增独立 HTTP 服务与 Artifact 历史查询；
- 新增单元、集成和真实模型可选冒烟测试。

验收：

```text
输入 eufy 家庭安防生态研究 Brief
→ 生成多个随证据变化的解决方案候选
→ 至少能够表达 ecosystem_service
→ 证据不足时减少候选并提出补研问题
→ 不使用固定门铃模板凑数
```

### 分支 6：`workflow/ai-native-ecosystem-gate`

目标：阻止普通功能包装成“AI 原生生态方案”。

任务：

- 实现确定性字段与引用校验；
- 实现 `scope_level`、跨设备、AI removal test、反馈闭环检查；
- 检查模型职责与确定性职责是否分离；
- 检查隐私、权限、fallback 和部署前验证计划；
- 对语义性判断生成 Human Gate 摘要；
- 失败时创建定向 RevisionRequest；
- 与通用 Source Recovery 对接；
- 添加主路径路由和 Checkpoint 测试。

验收：

```text
只有“生成通知文案”的候选被阻止
→ 单设备固定规则候选不能冒充生态服务
→ 缺少权限/fallback/验证计划的候选被阻止
→ 通过候选具有明确 AI 必要性和跨设备闭环
```

### 分支 7：`agent/technical-feasibility`

目标：回答“现有 eufy 能力是否足以支撑该生态方案和首个 Demo”。

任务：

- 消费 Ecosystem Opportunity 和 Device Capability Graph；
- 检查数据是否存在、接口是否可用、是否需要新硬件；
- 检查端侧/HomeBase/云端部署位置；
- 检查延迟、算力、网络、隐私、权限与失效模式；
- 区分 `demo_feasible`、`conditionally_feasible`、`insufficient_evidence`、`not_feasible`；
- 输出 Capability Gap 和 Source Requirement；
- 前沿论文只能作为技术成熟度证据之一，不能替代真实设备/API 验证；
- 所有事实性结论带 Evidence IDs；
- 通过通用补研流程请求企业 API 文档、内部测试或用户资料。

验收：

```text
候选需要包裹状态、人员身份、在家状态和天气
→ 系统逐项映射能力来源
→ 不可用能力进入缺口
→ 输出可做 Demo、附条件可做、证据不足或不可行
→ 不因模型乐观描述直接判定可上线
```

### 分支 8：`agent/security-policy-compiler`

目标：把用户安全目标生成受限、可审计的跨设备策略草案。

任务：

- 定义 Security Policy DSL；
- 模型只生成结构化意图和解释；
- 确定性 Compiler 生成规范 DSL；
- Validator 校验设备、能力、权限、死规则、fallback 和版本；
- 敏感动作默认需要人工批准；
- 支持 dry-run，当前阶段不直接控制真实设备；
- 保存 Policy Artifact 版本和差异；
- 失败返回具体 Gap，不返回假成功。

验收：

```text
用户输入包裹保护目标
→ 系统基于当前家庭能力图生成策略
→ 不存在的设备引用被拒绝
→ 敏感动作没有权限时被拒绝
→ 策略可以展示、审计和版本对比
```

### 分支 9：`workflow/security-policy-verification`

目标：上线前动态生成并执行验证矩阵。

任务：

- 定义 Verification Plan、Scenario、Run 和 Result；
- 至少覆盖 normal、boundary、failure、adversarial；
- 场景数量按策略动态生成，设置预算上限；
- 支持历史事件、用户授权素材、企业测试数据和模拟事件；
- 严格标记 provenance；
- 预期结果由策略目标/人工标准确定；
- 计算误升级、漏升级、不可判断和降级是否正确；
- 失败生成 RevisionRequest 并只重跑受影响策略；
- 高风险失败阻止 Scenario Gate；
- 添加用户对测试结果的质疑入口。

验收：

```text
同一包裹策略运行多类动态场景
→ 输出每个场景的输入来源和结果
→ 家人取件误报会导致失败
→ 遮挡无法判断时正确降级可通过对应测试
→ 失败后修改策略并生成新版本差异
```

### 分支 10：`agent/commercial-evaluation-v2`

目标：在技术和验证边界明确后判断是否值得继续上架验证。

不要恢复旧的加权总分。建议输出三个独立结论：

- 用户价值是否得到 Evidence 支持；
- 商业模式和收益假设是否值得验证；
- 交付与运营条件是否可以承受。

建议状态：

```text
recommend_for_validation
conditional
needs_more_evidence
do_not_recommend
```

规则：

- `recommend_for_validation` 不等于批准正式上架；
- 用户价值必须引用用户研究 Evidence；
- 商业结论必须引用市场、价格、渠道或企业数据 Evidence；
- 技术交付直接消费 Technical Feasibility Artifact，不重复让商业模型猜技术；
- 缺少销量、成本、退货、支持成本或订阅意愿时发起通用补研；
- 企业内部数据可以脱敏为区间或等级；
- 禁止使用模拟数据证明真实收益。

当前 `agent/commercial-evaluation` 分支的草稿只能作为参考，API 和输入必须按 v2 重做。

### 分支 11：`agent/redteam-policy-revision`

目标：同时支持系统红队和用户质疑，并形成定向返工。

任务：

- 红队攻击用户需求、竞品差异、技术、商业、隐私与安全假设；
- 用户可以输入自己的疑问；
- 每个疑问定位 Claim、Evidence、Opportunity、Policy 和 Scenario；
- 回答不了时不能生成空洞解释，必须创建 Gap；
- 识别 `affected_task_ids` 并恢复对应 Checkpoint；
- 只重跑受影响 Agent；
- 保存 Artifact 新版本和前后差异；
- 如果所有候选被否决，输出“当前不建议立项 + 最小补研/转向条件”，不能空白结束。

验收：

```text
红队提出“家人取件误报”
→ 定位包裹策略和相关场景
→ 只重跑 Policy/Verification
→ 新版本改变规则或承认不可解决
→ 展示前后差异
```

### 分支 12：`demo/package-goal-to-guard`

目标：以包裹保护证明完整生态闭环，而不是只演示风险分类。

Demo 至少展示：

1. 用户输入安全目标；
2. 读取或填写家庭设备清单；
3. 能力映射与盲区提示；
4. 自动生成跨设备策略；
5. 动态生成测试场景；
6. 运行测试并暴露一次失败；
7. 红队或用户质疑触发返工；
8. 策略新版本通过或降级；
9. 用户批准；
10. 输出“可进入试点 / 有条件试点 / 不建议试点”。

当前阶段默认 dry-run，不得声称已经控制真实 eufy 设备。未来获得企业设备 API 后，再增加真实 Deployment Adapter。

### 分支 13：`integration/eufy-device-api`

该分支必须等待企业明确提供接口和授权后再做。

需要企业提供或确认：

- 用户授权流程；
- 设备清单和型号；
- 设备在线、电量、网络等状态；
- 结构化检测事件；
- 门磁、锁、报警等传感器/动作能力；
- HomeBase 可部署能力；
- 测试环境或沙箱设备；
- 数据保留和隐私要求；
- 敏感动作权限与审计；
- API 限流、错误码和版本策略。

没有接口时必须使用 Capability Graph + dry-run，不得用 Mock 冒充真实联调成功。

### 分支 14：`backend/e2e-ecosystem-hardening`

目标：完成生产主路径、最终报告、Trace、恢复和发布验收。

任务：

- 把真实领域 Agent 接入 HTTP 项目生命周期；
- 统一 SSE 运行事件；
- 完成三个 Human Gate 的真实恢复；
- 最终报告中每个事实 Claim 必须有 Evidence ID；
- 输出 Opportunity、Capability、Policy、Scenario、商业结论和红队版本；
- 添加强制失败恢复；
- 添加端到端验收和前端投影；
- 再接飞书 Aily、审批和文档沉淀。

---

## 7. 需要修改的具体代码位置

### 7.1 API 与 Schema

- `docs/api/openapi.yaml`
  - 所有新公共 API 先在这里定义；
  - 不要继续扩大旧 Commercial v1 契约；
  - 为新 Artifact 使用独立 schema name/version；
  - 明确 `/api/v2` 是目标契约，而当前可运行 HTTP 主要是 `/api/v1`。

- `src/backend/app/schemas/innovation.py`
  - 当前以 Event Understanding、分数和单个 Innovation 为中心；
  - 保留旧模型兼容；
  - 新增或拆分生态 Opportunity 模型；
  - 不要强行给生态方案计算一个看似精确的总分。

- `src/backend/app/workflows/contracts.py`
  - 增加新 AgentType；
  - 保持 `artifacts` 泛型合并机制；
  - 增加必要的 Gate/Directive 投影，不要把完整家庭隐私数据塞进 ResearchState。

- `src/backend/app/schemas/source_recovery.py`
  - 增加 ecosystem opportunity、technical feasibility、policy verification 等 AgentType；
  - 新增 `affected_opportunity_ids`、`affected_policy_ids`、`affected_scenario_ids`；
  - 保持通用 Gap 前端契约。

### 7.2 Agent 与应用服务

- `src/backend/app/agents/product_technical/`
  - 保留 v1；
  - 提取可复用的 Evidence 引用校验和 Context 预算；
  - 不建议原地改名，否则已有 API、Artifact 和测试全部发生语义漂移。

- 建议新增：

```text
src/backend/app/agents/ecosystem_opportunity/
src/backend/app/agents/technical_feasibility/
src/backend/app/agents/security_policy/
src/backend/app/agents/commercial_evaluation_v2/
src/backend/app/agents/redteam/
```

- 建议新增应用服务：

```text
src/backend/app/application/ecosystem_opportunity/
src/backend/app/application/device_capabilities/
src/backend/app/application/security_policy/
src/backend/app/application/policy_verification/
```

LLM Adapter、确定性 Validator、数据库 Repository 和 API Service 必须分离。不要让 Prompt 直接承担权限校验、Evidence Gate 或数据库写入。

### 7.3 主图与任务规划

- `src/backend/app/workflows/planning.py`
  - 更新任务依赖；
  - Planner 输出必须包含新 Agent；
  - 不再默认 Product Technical 后直接进入 Commercial。

- `src/backend/app/workflows/graph.py`
  - 新增 ecosystem opportunity；
  - 新增 AI Native Gate；
  - 新增 technical feasibility；
  - 将 validation 改为或路由到 policy verification；
  - 保留商业、红队、Scenario Gate 和 Final Gate；
  - 定向返工必须能够只重跑 Opportunity、Capability、Policy 或 Verification。

建议的新图：

```text
Brief Gate
→ Research Planner
→ User Research + Competitor A2A
→ Evidence Readiness
→ Ecosystem Opportunity
→ AI Native Gate
→ Technical Feasibility
→ Commercial Evaluation v2
→ Red Team
→ Candidate Synthesis
→ Scenario Gate
→ Security Policy Compiler
→ Policy Verification
→ Final Synthesis
→ Final Gate
```

如果 Policy Verification 失败：

```text
资料不足 → Universal Source Recovery
策略错误 → Policy Compiler Revision
设备能力不足 → Technical Feasibility Revision
机会定义错误 → Ecosystem Opportunity Revision
商业假设不足 → Commercial Source Recovery
达到迭代预算仍不能解决 → inconclusive / do_not_recommend
```

### 7.4 Prompt 注册与运行时

- `src/backend/app/main.py`
  - 注册新 Prompt；
  - 注册新 Internal Model Adapter；
  - 未绑定 Adapter 时保持明确失败，不能落到 FakeAgent；
  - 模型选择继续使用现有 Model Gateway。

- `src/backend/app/core/config.py`
  - 为新 Agent 增加可选 runtime/model 配置；
  - 不在代码中写 API Key；
  - 本地 `.env` 不提交。

### 7.5 数据库

Artifact 仍可利用通用 Artifact Store，但以下内容建议建立独立持久化：

- 用户授权 Home Profile；
- Device Capability Graph 版本；
- Security Policy 版本；
- Verification Plan/Run/Scenario/Result；
- Deployment Approval 与 Rollback；
- Opportunity/Policy/Scenario 之间的不可变血缘。

每次数据库修改都要增加 Alembic migration，不允许只改 ORM Model。

---

## 8. 前端需要同步适配的页面

### 8.1 Research Brief 页面

输入对象从“某款未来产品”升级为：

- 研究行业/生态；
- 目标用户；
- 目标地区与时间范围；
- 已知目标产品和生态设备；
- 用户授权资料；
- 是否聚焦某类安全目标；
- 模型选择。

示例默认输入可以是“研究 eufy 家庭安防生态的未来 AI 原生机会”，但不能在后端 Prompt 中固定最终候选。

### 8.2 生态机会卡片

每个候选展示：

- `scope_level`；
- 用户安全目标；
- 依赖设备角色；
- 跨设备信息流；
- AI 必要性；
- 竞品差异证据；
- 技术假设；
- 已知盲区；
- Evidence coverage；
- Gate 状态；
- 补研按钮。

### 8.3 家庭设备与能力图

展示：

- 用户已授权设备；
- 每台设备提供的感知/动作能力；
- 数据是否本地；
- 当前在线/未知状态；
- 能力 Evidence；
- 方案要求但家庭缺少的能力。

不要向所有研究人员展示原始家庭视频或精确隐私信息。

### 8.4 策略页面

展示自然语言解释和受限 DSL 的可视化投影：

```text
触发事件
→ 状态
→ 上下文
→ 风险等级
→ 动作
→ 权限
→ 降级
```

### 8.5 验证矩阵

展示：

- 场景类型；
- 数据来源；
- 预期结果；
- 实际结果；
- 通过/失败/证据不足；
- 失败影响的策略；
- 返工前后差异。

模拟场景必须有明显的 `SIMULATED` 标签。

### 8.6 通用补研弹窗

继续复用现有 Universal Source Recovery：

- 告诉用户“当前缺什么”；
- 告诉用户“为什么需要”；
- 提供结构化文本填写；
- 允许上传文件、截图、PDF、字幕或授权资料；
- 允许企业内部数据填写区间或等级；
- 提交后显示 Evidence 回流和受影响 Agent；
- 不要求用户盲目更换另一个可能仍然无法解析的网站。

### 8.7 Human Gate

至少保留：

1. Research Brief Gate；
2. 生态候选/验证场景选择 Gate；
3. 最终建议 Gate。

产品 Demo 还需要独立 Deployment Approval：任何真实设备敏感动作必须再次确认，不能把研究审批等同于设备控制授权。

---

## 9. 测试与验收要求

每个分支至少执行：

```powershell
cd src/backend
python -m ruff check .
python -m mypy app
python -m pytest
```

优先在最低层增加测试：

- Schema/Validator：unit；
- Repository/Service/API：integration；
- LangGraph 路由、Checkpoint 和 Human Gate：workflow integration；
- 真实模型/API：可选 smoke，凭证缺失时明确 skip/blocked，不使用假成功；
- 完整 Goal-to-Guard：end-to-end acceptance。

必须覆盖的核心失败场景：

- 模型编造 Evidence ID；
- 候选只引用用户或只引用竞品证据；
- 候选声称设备具备未验证能力；
- Capability Graph 冲突；
- 策略引用不存在设备；
- 敏感动作没有权限；
- 模拟数据被误标为真实 Evidence；
- 场景测试失败但策略仍被批准；
- 所有候选被否决；
- 用户质疑无法回答；
- 资料补充后只重跑受影响节点；
- 模型 API、搜索、网页处理或设备接口超时；
- Checkpoint 恢复没有重复执行无关 Agent；
- 最终报告存在无 Evidence ID 的事实 Claim。

端到端验收应写入 `docs/acceptance-criteria.md`，最少包括：

```text
创建 eufy 生态研究项目
→ 资料接入与 Evidence 晋级
→ 用户和竞品研究并行
→ 生成动态生态候选
→ AI Native Gate 淘汰普通功能包装
→ 技术能力映射
→ 用户选择 Guardian Agent
→ 输入包裹保护目标
→ 生成策略和动态测试场景
→ 至少一次验证失败
→ 红队/用户质疑触发定向返工
→ 新版本通过、降级或明确不建议试点
→ 最终报告所有事实可追溯
```

---

## 10. 数据、隐私与安全要求

- 研究资料、用户家庭设备数据和运行时数据按项目/家庭隔离；
- 原始家庭视频不默认进入通用研究 Evidence Lake；
- 只保存策略所需的最少结构化事件和授权衍生产物；
- 用户必须能够撤销授权和删除家庭资料；
- 模型上下文不包含不必要的账号、地址或人脸身份；
- 原始视频、本地路径、API Key 和 Runtime Trace 不得提交到 Git；
- 对外报告只能显示脱敏统计和获得授权的 Evidence；
- 设备控制 Adapter 必须有 allowlist、审计、幂等和回滚；
- 开锁、报警、联系第三方等动作默认禁止自动执行；
- 模型只能提出动作建议，确定性策略和 Human Gate 决定是否执行；
- 设备离线、模型超时和证据冲突时优先安全降级。

---

## 11. 商业与“可落地”应该如何表达

最终报告不要只写“技术可行”，而应分别回答：

### 11.1 为什么可以从现在开始做

- 可以复用现有门铃、摄像头、门磁和 HomeBase；
- 第一阶段可以只做 dry-run 策略生成和验证，不控制真实设备；
- 模型负责开放目标理解，确定性代码负责安全执行；
- 包裹场景边界明确，适合做首个纵向切片；
- 设备/API 缺失可以通过 Capability Gap 明确暴露。

这些都是待 Evidence 验证的条件，不能仅凭 Prompt 写成事实。

### 11.2 相对优势假设

- eufy 有真实安防硬件和 HomeBase 本地执行入口；
- 相比纯大模型公司，更接近真实感知和动作闭环；
- 相比固定功能安防产品，可以把用户目标转成个性化策略；
- 经过验证的策略比直接生成自动化更适合安全场景；
- 本地执行可能形成隐私和延迟优势。

每一条仍需官方资料、企业内部信息或实验结果支撑。

### 11.3 商业结论的边界

没有企业内部数据时最多输出：

```text
值得进入用户与技术试点验证
```

不能输出：

```text
一定盈利
一定提高销量
一定降低退货
一定能够正式上架
```

正式商业判断需要补充：

- 目标用户规模；
- 订阅或硬件支付意愿；
- 模型与算力成本；
- 售后与误报成本；
- 设备兼容改造成本；
- 隐私与合规成本；
- 用户留存、退货和支持数据；
- 试点转化指标。

---

## 12. 如果所有候选或策略都失败

系统不能返回空白，也不能为了展示效果偷偷降低 Gate。

应输出以下结构：

```text
当前结论：不建议进入真实试点 / 当前证据不足

失败原因：
- 用户需求证据不足；
- 竞品已经完整覆盖；
- 当前设备无法观测关键状态；
- 隐私或动作风险不可接受；
- 模拟验证持续失败；
- 商业成本无法支撑。

最小补研或转向条件：
- 需要哪类用户证据；
- 需要哪个企业 API；
- 需要增加什么传感器；
- 需要怎样缩小使用场景；
- 需要修改哪个策略；
- 达到什么指标后可以重新评估。
```

这不是系统失败，而是“证据驱动立项系统”的有效输出。

---

## 13. 推荐的第一步

下一位开发者不要继续完成旧 `agent/commercial-evaluation`。

推荐顺序：

1. 检查当前工作树并保护未提交商业草稿；
2. 从 `main@0f611f1` 创建 `domain/ecosystem-opportunity-contract`；
3. 先修改 `docs/api/openapi.yaml`；
4. 新增生态机会 Schema 和兼容测试；
5. 更新 `docs/acceptance-criteria.md`；
6. 完成测试后再合并；
7. 然后进入 `evidence/device-capability-graph`。

第一步完成后，前端就可以开始设计：

- 生态机会卡片；
- AI Native Gate 说明；
- 设备能力图；
- 安全策略和验证矩阵的占位接口。

---

## 14. 接手开发者的 Definition of Done

整个新方向只有满足以下条件才算完成：

- 研究输入可以是 eufy 家庭安防生态，而不是必须指定一款未来硬件；
- 系统动态生成生态级方案，不固定输出包裹或 Guardian Agent；
- 候选结论受到真实 Evidence 约束；
- AI Native Gate 能淘汰普通 AI 包装；
- 设备能力来自授权 API、官方 Evidence 或用户确认，不靠模型猜；
- 用户安全目标可以转换成受限策略 DSL；
- 策略在部署前经过动态场景验证；
- 模拟、历史和真实测试数据严格区分；
- 红队和用户质疑都能触发定向返工；
- 无法落地时输出不建议与补研条件；
- 包裹 Demo 展示完整 Goal-to-Guard 闭环；
- 未获得企业设备 API 时明确保持 dry-run；
- 最终报告中没有无 Evidence ID 支持的事实 Claim；
- Ruff、Mypy、Pytest 和端到端验收全部通过；
- Secrets、个人数据、生成 Evidence 和 Runtime Trace 均未提交。

这份交接文档描述的是目标架构和迁移计划。除第 3 节明确列出的已完成内容外，其余内容不得向组员或导师表述为已经实现。
