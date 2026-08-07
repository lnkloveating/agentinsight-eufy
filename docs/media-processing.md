# 音视频处理与证据复核说明

## 当前链路

```text
用户上传并授权音频/视频
→ 校验 SourceAsset Hash 与项目隔离
→ PyAV 探测容器、时长和音视频流
→ 音轨标准化为 16 kHz 单声道 WAV
→ 视频按有界间隔抽取 PNG 关键帧
→ 保存产物 Hash、时间戳和媒体元数据
→ 显式 ASR/视觉 Connector（当前生产环境未配置）
→ 生成 derived Source Fragment
→ 人工对照音轨或帧审核
→ verified Fragment
→ 受控晋级 Evidence ID
```

## 为什么使用 PyAV

开发机和 GitHub CI 当前都没有系统级 `ffmpeg/ffprobe`。PyAV 官方为 Windows、Linux 和 macOS 提供带 FFmpeg 库的二进制 wheel，因此后端可以使用同一套版本完成真实解码，不依赖机器管理员另外安装命令行工具。项目固定使用 `av>=18,<19`，并通过 Pillow 输出审核用 PNG。

## 安全与资源边界

- 只读取已经进入项目隔离存储的本地 SourceAsset，不接受媒体 URL；
- 限制输入大小、媒体时长、流数量、解码视频帧数、保留关键帧数、图片尺寸和标准化音轨大小；
- 损坏容器、无音视频流、解码失败和资源超限都有独立错误码；
- 音轨和关键帧使用后端生成的固定 Artifact ID，API 不返回文件系统路径；
- 下载时重新计算 Hash，人工审核时再次核对 Fragment locator 中的 Artifact Hash；
- 删除 SourceAsset 同时删除媒体衍生产物、解析片段和派生 Evidence。

## 当前不能误解的能力

主办方当前提供的 GLM 5.2 和 DeepSeek V4 Pro 在模型目录中只声明文本与结构化输出能力，OpenCode 也未声明音频或视频能力。因此现在已经完成的是“真实媒体解码和可审核证据链”，不是“主办方模型已经能自动听懂/看懂视频”。

生产 `media_understanding_connector` 默认是 `None`。媒体预处理成功但没有 ASR/视觉 Connector 时，Collection Job 返回 `blocked`、错误码 `MEDIA_UNDERSTANDING_CONNECTOR_NOT_CONFIGURED` 和真实 `media_manifest`，不会生成假字幕或假画面描述。后续获得支持音频转写或视觉输入的 API 后，只需实现 `MediaUnderstandingConnector` 并显式注册；无需改动媒体存储、人工审核和 Evidence Gate。

## 前端适配

前端应分别显示：

1. 媒体预处理状态；
2. ASR/视觉 Connector 是否配置；
3. `derived` 片段待人工审核数量；
4. 保留音轨/关键帧预览；
5. 审核决定和审核后 Evidence 状态。

`blocked` 且错误码为 `MEDIA_UNDERSTANDING_CONNECTOR_NOT_CONFIGURED` 时，应展示“媒体已安全拆解，但尚无语音/视觉模型”，不能显示成“视频损坏”，也不能自动回退到文本模型猜测。
