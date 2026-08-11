# Security Policy Verification：后端与前端接入说明

## 作用和边界

本工作流把最新或指定版本的 `SecurityPolicyArtifact` 放进确定性 dry-run 引擎中验证。它把 DSL 当作
数据解释，不导入任何设备控制集成，也不发送真实通知。验证通过只表示当前结构化场景中的策略行为符合
断言，不表示产品已经上架、真实家庭已经部署或商业可行。

## 场景来源

后端自动为每条风险规则合成带时间戳的输入，并为每条策略强制运行五类失败降级：信号不可用、设备
离线、网络离线、状态不确定和权限拒绝。无法可靠合成的缺失或冲突条件会生成 `validation_gaps`，
不会伪造通过结果。

用户还可以提交结构化场景，但引用范围必须满足：

- `policy_id` 来自当前策略 Artifact；
- state/signal 引用已经由该策略声明；
- Evidence ID 已经进入源策略；
- 预期风险或预期动作至少提供一项。

## API

- `POST /api/v1/projects/{project_id}/workflows/security-policy-verification`
  - 可选指定 `policy_artifact_id`；省略时验证最新版本；
  - 可选提交最多 30 个用户场景；
  - 返回并持久化 `PolicyVerificationArtifact`。
- `GET /api/v1/projects/{project_id}/workflows/security-policy-verification/artifacts`
  - 查询所有验证版本。

## 前端展示

“场景实验”页展示策略版本、场景列表、输入信号、命中规则、风险变化、干预动作、fallback、断言和
Evidence 下钻。必须持续显示 `Dry Run，不控制真实设备`。

结果状态：

- `passed`：当前场景全部通过，主图进入等待商业评估；
- `conditionally_passed`：已运行场景通过但仍有验证 Gap，可限制试点范围并补研；
- `failed`：至少一个断言失败，主图进入等待策略修订；
- `inconclusive`：无法形成验证结论，不允许进入商业判断。

`validation_gaps` 已接入通用 Agent Gap/Source Recovery 投影，前端可复用统一补研弹窗。
