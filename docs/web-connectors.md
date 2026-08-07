# 授权网页连接器设计说明

## 定位

`evidence/web-connectors` 只解决一件事：把用户明确登记并授权研究的公开网页，转换成可保存、可定位、可复核的 Source Fragment。它不负责竞品结论，不调用业务 Prompt，也不把模型生成文字当成网页事实。

```text
用户登记公开 URL 并确认授权
→ URL、DNS、域名策略和 robots.txt 校验
→ 有界 HTTP 获取与逐跳重定向校验
→ UTF-8 HTML 项目快照
→ 可见文本确定性解析
→ 字符范围 + 行号 + Web Path 二次复核
→ Verified Source Fragment
→ 受控晋级 Evidence ID
→ 后续 OpenCode/内部模型只消费 Evidence
```

## 当前支持与明确不支持

当前支持静态公开 HTML、常见字符集、有限重定向、robots.txt、响应大小限制、超时、可选域名白名单、登录页拦截、项目隔离快照和删除清理。

当前不支持：

- 用户登录、Cookie 或私有会话；
- JavaScript 浏览器渲染；
- 验证码、Cloudflare 或指纹绕过；
- 站点级批量爬取和自动发现链接；
- 图片、音频和视频内容解析；
- OpenCode 自行联网补全缺失网页。

遇到这些情况时 Collection Job 必须返回 `blocked` 或 `failed` 和覆盖缺口，不能伪装成成功。生产部署还应配置网络出口规则，阻止对内网、云元数据和保留地址的访问。

## Crawlo 评估

[Crawlo](https://github.com/crawl-coder/Crawlo) 的异步下载、调度、重试、并发控制、HTTP/浏览器分层等设计对后续扩展有参考价值。但本项目当前处理的是少量、用户明确授权的研究来源，优先级是证据快照、来源审计和安全边界，而不是大规模抓取吞吐。

因此当前不把 Crawlo 作为核心依赖，也不采用其隐身浏览器、Cloudflare 绕过等能力。这样能减少依赖和合规风险，同时保留未来新增 `BrowserWebConnector` 的接口位置；只有静态 HTTP 无法覆盖且业务确认有授权时，才单独评估浏览器渲染分支。

## OpenCode 和模型的边界

当前只保留 OpenCode 外部 Runtime。OpenCode 使用主办方配置的模型，但网页连接器本身不消耗模型 API Key。两者关系是：

```text
Web Connector 获取并验证事实原文
→ Source Fragment / Evidence ID
→ OpenCode 或内部模型做语义研究
→ Claim 必须引用 Evidence ID
```

当前两个模型以及未来新增模型、多个 API Key 的选择属于 Model Gateway 和 Runtime 配置，不属于 Web Connector。前端应分别展示“资料处理状态”“OpenCode 可用状态”和“模型选择”，不要把它们合并成一个含义模糊的开关。
