# Security Policy Compiler：后端与前端接入说明

## 本分支完成什么

本分支把已经通过 AI Native Gate 和技术可行性验证的生态机会，编译成版本化、可解释、可审计的
家庭安防策略 DSL。它只输出 `dry_run` 策略，不连接和控制真实家庭设备。

模型只负责提出状态变量、授权信号请求、风险规则和干预阶梯。后端确定性 Compiler 负责权限校验、
设备角色校验、Evidence ID 校验，并生成稳定 ID、版本、语义 Hash、安全不变量及五类失败降级：

- 信号不可用；
- 设备离线；
- 网络离线；
- 状态不确定；
- 权限被拒绝。

高影响动作必须要求人工批准；Brief 未授权的信号、设备角色或动作会使本次 Agent 运行明确失败，
不会被静默改写成可执行策略。

## API

- `POST /api/v1/projects/{project_id}/agents/security-policy-compiler`
  - 输入：`selected_opportunity_ids`；
  - 输出：`SecurityPolicyArtifact`。
- `GET /api/v1/projects/{project_id}/agents/security-policy-compiler/artifacts`
  - 输出所有已持久化版本及版本差异。

主工作流在技术可行性通过后自动运行该 Agent，完成后停在
`awaiting_policy_verification`。下一分支应实现策略仿真和验证，而不是开启真实设备控制。

## 前端展示建议

前端可展示策略名称、持续状态、所需设备角色、授权信号、风险规则、干预阶梯、五类降级、Evidence
下钻、技术前置条件和版本差异。页面必须持续显示 `dry_run`，不能把 Artifact 表述成已部署策略。
