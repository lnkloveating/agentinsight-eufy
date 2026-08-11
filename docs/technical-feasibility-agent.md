# 技术可行性 Agent：后端与前端接入说明

## 1. 作用

技术可行性 Agent 只处理 AI Native Human Gate 已批准的生态机会。它不重新发明候选，也不判断商业
收益，而是回答：现有设备能力、数据、API、部署、性能、隐私、权限和离线降级是否足以支持一个受限
Demo。

模型负责拆解架构、技术需求、失败模式和补研问题；最终 `verdict` 由后端根据受控 Evidence 与
Device Capability Graph 确定，模型不能直接填写。

## 2. 输入与真实链路

```text
Human Gate 选中的 opportunity_ids
+ 最新 EcosystemOpportunityArtifact
+ ResearchHandoff 与统一 Evidence Retrieval
+ Device Capability Graph
+ 已解决的 Source Recovery Evidence
→ Model Gateway 结构化技术分析
→ Evidence ID 范围校验
→ 后端逐项核对 required_capabilities
→ 确定性 verdict、Gap、Coverage
→ 版本化 TechnicalFeasibilityArtifact
```

公开接口：

```http
POST /api/v1/projects/{project_id}/agents/technical-feasibility
GET  /api/v1/projects/{project_id}/agents/technical-feasibility/artifacts
```

POST 请求只提交 1–5 个经过 Gate 选择的 `selected_opportunity_ids`。模型仍由项目 `/models` 选择策略
决定，前端不传 Key。

## 3. 结论语义

- `demo_feasible`：所有已声明技术需求与必需设备能力均有支持证据，可以进入受限 Demo；
- `conditionally_feasible`：能力存在，但受授权、生命周期、网络或离线降级条件约束；
- `insufficient_evidence`：没有足够证据，不等于不支持；系统生成稳定补研 Gap；
- `not_feasible`：存在明确不支持或冲突证据，当前机会不能冒充可落地。

论文或模型常识只能支持一般技术背景，不能证明 eufy 设备或企业 API 已经具备某项能力。没有证据时
状态必须保持 `unknown`。

## 4. 主工作流与补研

AI Native Gate 批准后，工作流动态加入 Technical Feasibility Task，避免 Research Manager 在尚未选择
机会时提前规划错误范围。

```text
AI Native Human Gate approve
→ Technical Feasibility
   ├─ 至少一个 demo/conditional → awaiting_security_policy
   ├─ evidence insufficient      → 通用 Source Recovery → 只重跑技术 Agent
   └─ 全部 unsupported/conflict → inconclusive
```

补研问题来自当前 Artifact，例如“哪份已授权 API 文档能证明事件接口可用”“真实 HomeBase 延迟和离线
行为是什么”。用户提交文本、文档或内部测试后，内容按现有 Source Recovery 进入 Evidence Lake，不能
伪装成官网事实。

## 5. 前端展示

每个选中机会展示：

- 架构与受限 Demo 范围；
- data/interface、deployment、performance、privacy、permission、resilience、hardware 等需求；
- 每项 `supported / conditional / unknown / unsupported / conflict` 与 Evidence IDs；
- Device Capability Graph 匹配的设备及条件；
- 失败模式、限制、补研问题和最终确定性 verdict。

`insufficient_evidence` 应显示“需要补充资料”，不能显示 Failed；`not_feasible` 才表示已有反证。进入
`awaiting_security_policy` 只说明技术上可开始受限验证，仍不代表商业可行、可上架或最终推荐。

## 6. 不在本分支范围

- 不生成跨设备安全策略；
- 不执行动态场景验证；
- 不判断收入、成本或上架；
- 不替代企业设备 API；
- 不使用假设备数据冒充联调。

下一分支是 `agent/security-policy-compiler`。
