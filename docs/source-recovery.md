# Source Recovery Orchestration

## 目标

当授权网页或媒体资料解析失败，或处理成功但没有覆盖当前研究所需信息时，研究流程不能直接
卡死，也不能通过模型猜测缺失事实。后端创建一个可审计的资料恢复任务，告诉前端“为什么
失败、缺哪些具体内容”，让用户直接补充内容后重新评估资料准备度。

主流程：

```text
Source Asset 处理失败或有效信息不足
→ POST /projects/{project_id}/source-recoveries
→ 后端读取 Collection Job 与 Source Requirements
→ 返回失败原因、缺失字段和受影响 Agent
→ 前端展示结构化补充弹窗
→ 用户提交具体内容并确认授权与准确性
→ user_input Source Asset
→ succeeded Collection Job
→ verified Source Fragment
→ manual confirmed Source Routing
→ partially_verified user_declaration Evidence
→ Source Requirements 重新评估
→ 返回 targeted_retry 或继续等待补充
```

替代链接、上传文件可以继续使用已有 Source API，但不是恢复任务的主要入口。恢复接口不会
重新访问原网站、调用 OpenCode、调用业务模型或创建虚构资料。

竞品研究优先从 Source Requirements 自动生成产品、价格和评价字段。对于当前
Source Requirements 尚未覆盖的用户研究、产品技术或商业任务，受信任的工作流主管可以在
创建恢复任务时传入 `missing_questions` 和 `affected_agent_types`；恢复服务只校验并持久化
这些缺失问题，不在此处运行模型。未传问题时会根据原 Source Asset 的用途生成一个通用问题。

## 前端弹窗契约

创建恢复任务后，前端主要读取：

- `status`：是否等待输入、仍缺资料、已解决、带缺口继续或取消；
- `reason_code` / `reason_message`：可直接转换为失败提示；
- `requested_fields`：字段标题、问题、是否必填、产品、地区和 Claim 类型；
- `current_assessment`：当前 Source Requirements 缺口；
- `resume_directive`：后端是否允许继续，以及只影响哪些 Agent/任务。

前端不应要求用户盲目更换网站。主操作是“补充缺失信息”，上传文件、粘贴原文或换链接只作为
辅助方式。用户不知道某字段时可以不提交该字段，随后继续补充，或通过人工决定选择
`proceed_with_gaps`。

## 证据和血缘规则

用户填写的内容：

1. 必须确认授权依据和内容准确性；
2. 保存为 `kind=user_input` 的 Source Asset，而不是官网网页；
3. 每个答案保存精确 JSON Locator 与原文 Fragment；
4. Evidence 使用 `source_type=user_declaration`，初始状态为 `partially_verified`；
5. Recovery 同时保留原失败 Source Asset、Collection Job、替代 Source Asset 与 Evidence IDs；
6. 最终事实仍必须引用 Evidence ID，并展示其真实来源类型；
7. 选择带缺口继续不会生成任何 Evidence，也不能把未知项改写成否定事实。

## 定向恢复

`resolved` 和 `proceeding_with_gaps` 才会返回可执行的 `resume_directive`。工作流通过
`prepare_source_recovery_resume` 将受影响 Agent 类型映射到当前 Task Plan，只产生对应
`affected_task_ids`。现有 LangGraph 定向返工路径会跳过未受影响的用户研究或竞品研究节点。

资料恢复服务本身不直接启动模型调用；它保存事件和恢复指令，由当前项目的工作流主管在有效
Checkpoint 上消费。这避免 API 请求重复触发 Agent，也保留后续飞书审批和重试的统一入口。

## 产品技术候选补研

产品技术 Agent 生成候选组合后，如果少于三个候选通过 Gate，或某个候选仍缺用户事件、竞品
差异、上下文信号、数据接口等证据，后端会在 `portfolio_gaps` 中返回稳定的 `gap_id`。前端可
按用户选择的缺口调用：

```http
POST /api/v1/projects/{project_id}/agents/product-technical/artifacts/{artifact_id}/source-recovery
```

后端把缺口确定性转换为 `requested_fields`，字段会带上证据类型提示、受影响候选 ID、Claim
类型和建议路由。这里不再次调用模型，也不要求用户提供一个可能仍被反爬拦截的新链接；弹窗
主操作是让用户或企业填写当前判断真正缺少的事实，并说明适用范围、限制和信息来源。

用户提交并确认授权与准确性后，答案沿用统一资料恢复链路生成 `user_declaration` Evidence。
Recovery 保存 `source_artifact_id → source_gap_ids → submission → evidence_ids` 的完整血缘，并
返回受影响的用户研究、竞品研究或产品技术任务。下一次运行产品技术 Agent 时，已解决补研
产生的 Evidence 会加入受控 Evidence Context；Validator 仍会检查 Evidence ID，不能因为用户
填写过内容就绕过引用门禁。旧版没有 `gap_id` 的产品技术 Artifact 会在读取时生成相同的稳定
ID，不需要迁移历史 Artifact 内容。

## 明确不包含

- 绕过 robots.txt、验证码、登录页或反爬限制；
- 把用户声明伪装成官网或第三方证据；
- 为扫描 PDF、截图、视频补造 OCR、ASR 或视觉理解能力；
- 自动重新运行整个研究项目；
- 用 Mock 内容填满缺失字段。
