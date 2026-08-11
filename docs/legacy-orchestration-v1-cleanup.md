# Legacy Orchestration v1 清理说明

## 清理目标

当前 AI 原生家庭安防主图已经由生态机会、技术可行性、安全策略、dry-run 验证和 Commercial
Evaluation v2 组成。旧单产品时期预留的三个泛化角色没有真实 Adapter、Prompt、Artifact 契约或主图节点，
继续保留只会让前端和后续开发误以为它们仍会运行。

本次删除：

- `candidate_synthesis`；
- `validation`；
- `final_synthesis`；
- 上述角色的 Context Policy、Runtime 展示名称、Source Recovery 公共枚举和测试 Runtime 占位；
- 旧版只有 `decision/severity/required_actions` 的 `RedTeamDirective` 及其解析器；
- 本地遗留的 Product Technical Python 字节码缓存。

## 明确保留

- `red_team` 正式角色：下一分支会定义证据约束、用户质疑、策略攻击和定向返工的 v2 契约；
- Scenario 与 Final Human Gate：它们属于后续审批，不等于已删除的泛化 Agent；
- `ready_for_product_technical` 输入别名：仅用于读取已有旧 Checkpoint，新状态不会输出它；
- Evidence、Source Recovery、Artifact Store、Model Gateway 和 Runtime Gateway 公共底座；
- 历史方向文档：保留用于解释为什么从单产品转向 AI 原生生态，不参与运行。

## 当前主路径

```text
Research Brief
→ User Research + Competitor Ecosystem
→ Ecosystem Opportunity
→ AI Native Gate
→ Technical Feasibility
→ Security Policy Compiler
→ Policy Verification
→ Commercial Evaluation v2
→ Red Team Policy Revision（下一步）
→ Goal-to-Guard Demo
→ Final Human Gate / Report Assembly
```

最终报告将由后续 E2E 阶段按照强类型 Artifact 确定性装配，不恢复没有证据边界的 `final_synthesis` v1
Agent。新版红队必须重新定义 Contract，不能复用已删除的宽松 Directive。
