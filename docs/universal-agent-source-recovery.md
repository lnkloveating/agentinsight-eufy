# Universal Agent Source Recovery

## 目标

把用户研究、竞品研究、产品技术以及后续商业评估、红队的原生资料缺口投影成同一套前端
补研契约。前端不需要理解每个 Agent 的私有 JSON 结构，只需展示问题、缺口原因、严重度、
建议资料类型和受影响对象。

```text
Agent Artifact 原生 research_gaps / portfolio_gaps / future gaps
→ 确定性 AgentGap 投影（不调用模型）
→ 用户选择需要补研的 gap_id
→ Source Recovery 弹窗
   ├─ 直接填写事实
   └─ 上传文件 / PDF / 授权链接后绑定已晋级 Evidence
→ 重新评估
→ 只恢复 affected_task_ids / affected_agent_types
```

## 公共接口

```http
GET  /api/v1/projects/{project_id}/agents/{agent_type}/artifacts/{artifact_id}/gaps
POST /api/v1/projects/{project_id}/agents/{agent_type}/artifacts/{artifact_id}/source-recovery
POST /api/v1/projects/{project_id}/source-recoveries/{source_recovery_id}/evidence-submissions
```

旧的产品技术补研接口继续可用，并委托给同一个通用服务。

统一 `AgentArtifactGap` 包含稳定 `gap_id`、Artifact/Task/Agent 身份、问题、原因、严重度、建议
资料类型、必须证据类型、受影响候选、研究对象、维度和原始 JSON 路径。已有后端生成的
`gap_id` 会原样保留；没有 ID 的旧 Agent 缺口按语义字段生成稳定 Hash，不依赖 Artifact 版本号。

## 资料输入边界

直接填写仍沿用已有 Source Recovery Submission：用户必须确认授权和准确性，后端将内容保存为
`user_declaration`、`partially_verified` Evidence，并保留 Source Asset、Fragment 和 Submission
血缘。

文件、PDF、网页或 API 文档不能直接绑定原文件。前端应先调用既有 Source Ingestion、
Processing、Routing 和 Fragment Evidence Gate；只有同项目、同 Source Asset 且状态为
`verified` 或 `partially_verified` 的 Evidence 才能绑定恢复字段。绑定不会复制或重新生成
Evidence，因此共享检索会直接看到同一条事实记录。

当前 Evidence 绑定接口一次接收一个 Source Asset。若多个资料共同补齐缺口，可分别提交；
每次提交都有独立 request ID，重复请求保持幂等。

## 定向恢复

恢复任务始终包含产生缺口的 Agent Task。若缺口类型指向上游用户、竞品、技术或商业事实，
服务只从该 Artifact 的输入血缘中加入对应任务。任务解决后返回 `targeted_retry`；资料仍不足时
保持 `needs_more_information`；用户也可以明确选择 `proceed_with_gaps`，但未知项必须继续展示。

本分支只生成恢复指令，不直接执行 LangGraph 重跑。后续工作流编排节点消费
`resume_directive`，从对应 Checkpoint 恢复。

## 安全与确定性

- Agent 类型必须与 Artifact 的真实类型一致，跨项目 Artifact 返回不存在；
- Gap 只能来自持久化 Artifact，前端不能凭空创建 Agent Gap；
- Evidence 必须来自指定已登记 Source Asset，项目、状态和 Claim 类型均需通过校验；
- `unverified`、`outdated`、`mock`、`invalid` 和 Agent 推断不能作为直接事实补研；
- 投影、字段路由、Evidence 校验和恢复范围都不调用大模型；
- Artifact、Evidence 和既有研究结果保持不可变。

