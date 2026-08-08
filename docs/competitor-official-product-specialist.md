# 竞品官方产品专家

## 能力边界

`Official Product Specialist` 是竞品 A2A 系统中第一个真实业务专家。它只分析已经由
用户或企业授权、经过 Source Processing 并晋级到 Evidence Lake 的官方资料，不主动
搜索互联网，也不把模型训练知识当作事实来源。

```text
授权官方网页/文件
→ Source Fragment
→ 人工或受控规则晋级 Evidence
→ OfficialProductEvidenceContextBuilder
→ Competitor Supervisor 的 EvidenceRequest
→ OfficialProductModelSpecialistAdapter
→ Model Gateway（项目选择的模型）
→ 确定性引用、范围和质量校验
→ A2A Task + CompetitorSpecialistArtifact
```

生产启动会把 `official_product` 专家绑定到真实 Model Gateway。当前项目可选择主办方的
GLM 5.2 或 DeepSeek V4 Pro；API Key 只从后端环境读取，不会进入 Prompt、Artifact、
事件或前端响应。价格渠道与用户评价专家仍然保持未绑定并明确返回
`specialist_not_bound`。

## 输入证据规则

- 只读取当前项目内 `verified` 或 `partially_verified` 的 Evidence；
- 只接受 `vendor_claim` 和 `fact` Claim 类型；
- 每次模型调用使用有上限的 Evidence Context；
- Prompt 中保留 Evidence ID、原文、来源和产品范围；
- 不分析价格、渠道库存、用户口碑或未来尚未发布的产品；
- “资料没有说明”只能记为未知项或补研问题，不能改写成“产品不支持”。

## 输出与门禁

模型输出必须符合 `official_product_intelligence` 结构，包含产品身份、型号、能力、规格、
兼容性、限制、可用性、矛盾项、未知项和补研问题。确定性 Validator 会在保存前检查：

- 每个事实和摘要引用的 Evidence ID 都属于本次受控上下文；
- `scope_label` 必须与主管请求的产品范围完全一致；
- 产品与事实 ID 不得重复；
- Evidence 覆盖、独立域名数、质量分和最终状态由代码计算，不由模型自行决定；
- 空证据返回 `blocked`，范围缺失或证据不足返回 `partial`，不得伪装成 `completed`。

父级竞品主管仍会并行调度三类专家。现阶段官方产品专家可以成功交付，但另外两个专家
未绑定，所以父级竞品 Artifact 按设计保持 `partial`。完整竞品能力矩阵要等价格渠道、
用户评价和综合审计分支完成后才能生成。

## 前端联调

本分支没有新增公共 HTTP API，因此 `docs/api/openapi.yaml` 不变。前端可以继续通过既有
Agent Run 和 SSE 事件展示 `official_product` 子任务的运行、完成、失败或复用状态。当前
尚无 A2A Task 查询接口，页面刷新后的完整专家输出投影留给后续统一投影接口。

UI 应明确区分：

- 官方专家 `completed`：给定官方资料已完成结构化提取；
- 官方专家 `partial`：资料覆盖或独立来源不足；
- 父级竞品任务 `partial`：仍有其他竞品专家未完成；
- `blocked`：没有合格官方 Evidence，或专家未绑定；
- `failed`：模型、契约、超时或持久化发生真实错误。

## 验证

自动化测试：

- `tests/unit/test_official_product_agent_contracts.py`：Schema、引用、范围与状态门禁；
- `tests/integration/test_official_product_agent.py`：授权网页、解析、Evidence、真实 Model
  Gateway 契约、A2A 专家和模型审计的完整确定性链路；
- `tests/integration/test_competitor_a2a_gateway.py`：并行、错误分类、复用与定向恢复；
- `tests/integration/test_competitor_a2a_supervisor.py`：三类 EvidenceRequest 与父级聚合。

真实冒烟脚本：

```powershell
python scripts/smoke_official_product_live.py \
  --model anker:glm-5.2 \
  --url "https://www.eufy.com/products/t85m0j11"
```

该脚本使用临时数据库和临时资料目录，不保存生成证据或运行 Trace，也不会输出 API Key。
2026-08-08 已分别使用 GLM 5.2 和 DeepSeek V4 Pro 完成同一条授权 eufy 官方网页链路的
真实调用验证。
