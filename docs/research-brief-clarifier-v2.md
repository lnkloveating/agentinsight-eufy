# Research Brief 追问 Agent v2

## 目标

本模块位于“用户输入模糊目标”和“创建正式研究项目”之间。它不会从一句话直接猜出完整 Brief，
而是调用用户选择的模型逐轮追问，并由确定性后端检查 AI 原生家庭安防生态研究所需字段是否真的补齐。

示例入口：

```text
研究一下 eufy 未来的老人安防产品
```

系统应先询问研究范围、安全场景、可用信号、摄像头禁区、允许干预、资料权限和交付物，不能直接创建项目，
也不能默认用户允许上传家庭视频、识别老人身份、共享数据或自动联系第三方。

## 当前可用 API

```text
POST /api/v1/research-brief-clarifications
GET  /api/v1/research-brief-clarifications/{session_id}
POST /api/v1/research-brief-clarifications/{session_id}/messages
```

开始会话时可以提交 `/models` 返回的 `model_id`；省略时使用后端已配置且可用的默认模型。API Key 仍只在后端环境中读取。

响应包含：

- 完整对话；
- 强类型部分草稿 `draft`；
- 后端计算的 `missing_fields` 与 `validation_issues`；
- 当前一批动态问题；
- 模型、Token 和估算成本审计；
- 只有完整校验通过时才出现的 `completed_brief`。

前端提交回答时必须携带 `expected_version`。旧页面或并发标签页提交过期版本会得到 409，避免覆盖新回答。

## 模型与确定性代码的边界

模型负责：

- 从用户原话提取最小字段补丁；
- 根据当前草稿和缺失字段提出最多六个下一轮问题；
- 用自然语言解释为什么还需要确认。

后端负责：

- 只接受带用户消息 ID 血缘的字段；
- 拒绝未知字段、非法枚举、越界长度和错误类型；
- 逐项检查嵌套权限、隐私和干预边界；
- 使用正式 `ResearchBrief` Schema 做最终完整校验；
- 保存会话、模型调用、Prompt 版本、Token、成本和错误分类；
- 在字段未完成时保持 `awaiting_user`，不生成默认授权或假 Brief。

模型调用失败时会话保存为 `failed`，API 返回安全错误分类，不返回 Provider 原始错误、Prompt、Key 或思维过程。

## 前端建议

首页输入一句研究目标后，先创建追问会话。页面使用聊天区展示 `messages`，使用表单卡片展示 `questions`，右侧实时展示
`draft` 和“仍缺少什么”。状态为 `ready_for_confirmation` 后显示完整 Brief 确认页；用户确认后，再把
`completed_brief` 与模型策略提交给现有 `POST /api/v1/projects`。

不要在追问会话阶段展示研究进度、竞品结论或未来方案，因为此时正式项目和 Evidence 尚未创建。

## 不包含

- 不执行用户研究、竞品研究或机会生成；
- 不上传、解析或检索研究资料；
- 不自动创建正式项目或绕过 Brief Human Gate；
- 不根据模型常识生成 Evidence；
- 不把问题固定为老人、包裹或门铃模板。

## 后续顺序

```text
agent/research-brief-clarifier-v2（本分支）
→ agent/competitor-ecosystem-analysis
→ agent/ecosystem-opportunity
→ workflow/ai-native-ecosystem-gate
```
