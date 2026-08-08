# 搜索发现 Connector

## 目标

该模块在用户已经确认研究范围、但资料准备度仍有缺口时，发现可能值得接入项目的公开
网页。它解决的是“去哪里找资料”，不是“网页里有什么事实”。当前显式注册的真实
Provider 是 Tavily Search API；Provider 注册方式可扩展，但 API 不接受用户提交任意搜索
端点或执行命令。

```text
Source Requirements 缺口
→ Search Discovery Run
→ 候选 URL（candidate_only）
→ 后续 Competitor Discovery / 人工确认
→ 用户确认授权依据并创建 Source Asset
→ Web Processing + Source Routing
→ SourceFragment 人工审核
→ Evidence Lake
```

搜索结果的标题、URL、摘要和相关性分数只能用于候选筛选。它们不是 Source Asset、
Evidence、Claim 或 Agent Artifact，也不能直接满足资料准备度。

## API

```text
POST /api/v1/projects/{project_id}/source-discovery/searches
GET  /api/v1/projects/{project_id}/source-discovery/searches
GET  /api/v1/projects/{project_id}/source-discovery/searches/{search_discovery_run_id}
```

创建请求显式包含：

- `query`：发给搜索 Provider 的检索问题；
- `intent`：竞品候选、官方产品、价格渠道、用户评价或一般补研；
- `provider_id`：当前为 `tavily`，后续可注册其他固定 Provider；
- `max_results`：单次最多 20 条；
- `include_domains` / `exclude_domains`：可选的纯域名过滤器；
- `requested_by` / `purpose`：审计字段，不发送给 Provider。

运行状态包括：

- `succeeded`：Provider 返回并完成安全规范化；允许零条候选；
- `failed`：超时、网络、限流、Provider 5xx 或未分类错误；
- `blocked`：功能关闭、缺少密钥、认证失败、请求被拒或响应超过安全限制；
- `running`：已保存运行记录、正在等待 Provider；进程异常退出时不会伪装成功。

失败运行保存稳定 `error_code` 和 `retryable`，但不保存密钥、请求头或 Provider 错误正文。

## 本地配置

密钥只放入本地 `src/backend/.env`，不要提交：

```dotenv
SEARCH_DISCOVERY_ENABLED=true
SEARCH_DISCOVERY_TAVILY_CREDENTIAL_ENV=TAVILY_API_KEY
SEARCH_DISCOVERY_TIMEOUT_SECONDS=20
SEARCH_DISCOVERY_MAX_RESPONSE_BYTES=1048576
TAVILY_API_KEY=tvly-your-local-key
```

实现只调用 Tavily 的 `POST /search`，固定使用 `basic` 搜索，不请求生成答案、原始正文或
图片，也不调用 Tavily Extract/Crawl。缺少 `TAVILY_API_KEY` 时 API 会创建可审计的
`blocked` 运行，不会返回示例数据。

## 安全和证据边界

- 只保留规范化后的公开 HTTP/HTTPS URL，移除常见跟踪参数；
- 丢弃 localhost、私网 IP、无效 URL、重复 URL 和不符合域名过滤器的结果；
- 对查询、域名数量、返回条数、摘要长度、超时和响应字节数设硬限制；
- Provider Base URL 固定在代码中，避免通过配置把密钥发送到任意地址；
- 搜索摘要只标记为 `candidate_only`，不会写入 Source Asset、Evidence 或 Model Call；
- 搜索后的网页接入仍需单独确认授权依据并经过现有证据链路。

## 自动化验证

- `tests/unit/test_search_discovery_connector.py`：真实 Tavily HTTP 请求/响应契约、凭据、
  状态码、流式大小限制和域名校验；
- `tests/integration/test_search_discovery_api.py`：项目隔离、持久化、去重、安全过滤、
  失败审计，以及零 Source Asset、零 Evidence、零 Model Call 的门禁。

真实联网需要本地 Tavily API Key；自动化测试使用 HTTP Mock 验证同一请求和响应契约，
不会消耗额度或把密钥提交到仓库。
