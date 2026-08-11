# Red Team Policy Revision v2

## 目标

红队不重新生成产品机会，也不为方案背书。它同时消费用户研究、竞品生态、生态机会、技术可行性、
Security Policy、Policy Verification 和 Commercial Evaluation 七类 Artifact，主动寻找证据越界、
技术不可行、安全失败、隐私授权、误报漏报、离线降级、干预权限、商业夸大和“检测后通知伪装成
AI 原生”等问题。

模型负责提出语义攻击和回答用户质疑；后端负责 Evidence、ID、范围、最终 verdict、返工任务、版本差异
和循环上限。模型不能输出 verdict、RevisionRequest、任务 ID、分数或部署批准。

## 公共接口

```text
POST /api/v1/projects/{project_id}/agents/red-team-policy-revision
GET  /api/v1/projects/{project_id}/agents/red-team-policy-revision/artifacts
```

POST 请求可携带最多 20 条用户质疑。质疑可以只包含问题，也可以定位当前 Artifact、Policy 或 Scenario；
引用旧版本或其他项目 ID 会在调用模型前返回 422。每条质疑由后端生成稳定 `challenge_id`，模型必须恰好
回答一次，不能遗漏或替换问题。

## 结构化输出

- `findings`：每个事实性问题至少一个 Evidence ID，并定位当前 Artifact 与受影响 Agent；
- `challenge_responses`：回答、部分回答、无法回答或需要人工决定；
- `red_team_gaps`：具体缺什么、为什么需要、建议提供什么资料以及影响哪些 Agent；
- `revision_requests`：后端根据 Finding 生成，不接受模型自报 Task ID；
- `version_diff`：新增、已解决和仍存在的 Finding；
- `fallback_plan`：不可修复的 critical 问题被淘汰时，必须给出更小、更安全的范围与重新进入条件；
- `verdict`：由后端确定性计算。

Verdict 优先级：

```text
critical + irreducible → reject
隐私/授权/高风险动作需要人决定 → human_review
存在 Gap 或未回答质疑 → needs_more_evidence
存在可修订 Finding → revise
仅无阻断问题 → pass
```

`pass` 只允许进入 Goal-to-Guard Demo，不表示真实部署、上架或收益获批。

## 主图返工

```text
Commercial Evaluation v2
→ Red Team
   ├─ pass → awaiting_scenario_validation
   ├─ needs_more_evidence → Universal Source Recovery → Red Team
   ├─ revise → 定位最早受影响 Agent → 重跑该节点及下游 → Red Team
   ├─ human_review → awaiting_red_team_review
   └─ reject → 保存 fallback_plan 后结束
```

如果安全策略需要修改，只重跑 Security Policy、Policy Verification、Commercial 和 Red Team，不重复用户
研究、竞品、生态机会或技术 Agent。若用户或竞品事实本身被攻击，则从对应研究节点恢复并让下游重新汇合。
达到 `max_iterations` 后仍需补研或返工，主图返回 `inconclusive`，不能无限循环。

Source Recovery 用户提交的已验证 Evidence 会合并进共享 `ResearchHandoff.supplemental_evidence_ids`，下一轮
红队和其他领域 Agent 使用同一 Evidence Lake，不建立红队私有知识库。

## 前端展示

“反方挑战”页面建议展示：

- 九个自动攻击维度及覆盖状态；
- Finding 严重程度、Evidence 下钻和受影响 Artifact/Policy/Scenario；
- 用户质疑输入框及逐条回答状态；
- `补充资料 / 接受修订 / 人工决定 / 淘汰` 对应操作；
- RevisionRequest 的最早恢复 Agent 和下游重跑时间线；
- 新旧版本 Finding 差异；
- reject 时的安全降级方案和重新评估条件。

前端不得把模型生成的进度、未持久化 Finding 或旧版本结论显示成当前事实。
