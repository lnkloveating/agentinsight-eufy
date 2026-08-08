# 用户研究 Agent：后端与前端联调说明

## 当前能力

`agent/user-research` 已打通以下生产链路：

```text
授权网页或文件
→ SourceAsset
→ 确定性解析与 SourceFragment
→ 来源链复核
→ Evidence Lake
→ 受控 Evidence Context
→ Model Gateway
→ Agent Runtime
→ UserResearchArtifact
```

用户研究模型只负责在已有证据上识别用户事件链、当前应对方式、痛点、未满足需求、
样本偏差和补研缺口。Evidence 状态、引用合法性、独立来源数、质量分和最终任务状态
由后端确定性计算。

## 前端调用顺序

1. 创建项目并完成 Brief 审批，使项目进入 `researching`。
2. 通过 `/projects/{project_id}/sources/links` 或 `sources/files` 登记授权资料。
3. 调用 `POST /projects/{project_id}/sources/{source_asset_id}/processing`。
4. 分页读取 `GET .../fragments`，由研究人员确认片段含义与 Claim 类型。
5. 调用 `POST .../fragments/{source_fragment_id}/evidence` 晋升片段。
6. 调用 `POST /projects/{project_id}/agents/user-research` 启动用户研究。
7. 通过 `GET /projects/{project_id}/agents/user-research/artifacts` 读取历史版本。
8. 通过 `GET /projects/{project_id}/agents` 展示运行状态、模型、Token 与错误信息。

前端必须明确区分：

- `completed`：证据与研究章节都满足门禁；
- `partial`：模型已完成分析，但独立来源、用户意见或补研条件仍不足；
- `blocked`：没有任何可用 Evidence，模型不会被调用；
- HTTP `502/503/504`：Runtime、模型依赖或执行超时，不得回退到 Mock 结果。

## 证据边界

官网产品页应标记为 `vendor_claim`，可用于描述现有功能，但不能支撑用户痛点或未满足
需求。用户评论、访谈或授权反馈数据才可标记为 `user_opinion`。来源链验证只能证明
“这段文字确实来自该资料”，不能自动证明提交者选择的 Claim 类型正确，因此前端需要
保留人工确认步骤。

## 真实验证结果

2026-08-08 使用两份公开 eufy 产品页完成了真实烟雾测试：确定性 HTML 解析分别生成
372 和 475 个可回溯片段；`anker:glm-5.2` 与
`anker:deepseek-v4-pro` 都成功经过 Model Gateway、Runtime 和 Artifact Store。
由于输入是厂商资料，两次结果均正确返回 `partial`，没有伪造用户痛点，并列出补充
用户评论或访谈的研究缺口。

另外使用两个允许抓取的公开评价页面验证了 `user_opinion` 路径；模型能够生成带
Evidence IDs 的痛点与未满足需求。若仍存在高严重度补研缺口，后端继续保持
`partial`，不会仅因模型生成了完整字段就强行标为 `completed`。

可重复执行的本地烟雾测试：

```powershell
python scripts/smoke_user_research_live.py --probe-only
python scripts/smoke_user_research_live.py --model anker:glm-5.2
python scripts/smoke_user_research_live.py --model anker:deepseek-v4-pro
```

脚本使用一次性数据库和资料目录，结束后自动清理；不会打印密钥，也不会把网页快照、
Evidence、模型输出或 Runtime Trace 写入 Git。
