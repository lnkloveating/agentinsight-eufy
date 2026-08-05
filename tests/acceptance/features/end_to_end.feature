# language: zh-CN
功能: 以真实证据发现并验证事件理解型产品机会
  作为 eufy 产品经理
  我希望从飞书发起可审计的多 Agent 研究
  以便判断候选场景是否值得进入下一阶段产品验证

  场景: 从飞书 Aily 创建并确认研究任务
    假如用户在 Aily 提出一个模糊的北美智能家居研究问题
    当 Aily 追问市场、用户、品类、品牌、时间和约束
    并且用户确认结构化 Research Brief
    那么 Aily 应调用后端创建项目
    并且项目应暂停在 Brief 人工确认门或在确认后进入行业机会研究
    并且用户应获得 project_id 与 Deep Research Web 地址

  场景: 从行业机会形成候选事件理解场景
    假如项目已经通过 Brief 确认
    当用户研究 Agent 和竞品 Agent 使用真实 Evidence 完成研究
    并且产品技术 Agent 生成候选场景
    那么系统应比较 Package Risk Intelligence、Garage Door Risk 和 Loitering Context 或证据支持的等价候选
    并且每个候选应包含 Event、State、至少两个 Context、Inference、Risk 或 Value 以及 Action
    并且每项评分应保留理由与 Evidence IDs

  场景: 阻止伪事件理解候选晋级
    假如一个候选只检测包裹并发送送达通知
    而且该候选没有事件状态或两个上下文信号
    当 Event Understanding Gate 检查该候选
    那么候选应被标记为 needs_revision 或 rejected
    并且候选不得进入飞书场景晋级审批

  场景: 红队真实改变候选结果
    假如候选已经完成技术与商业评估
    当红队发现竞品差异未验证或关键数据源不可获得
    那么红队应降低对应分数并要求补研、修改或淘汰
    并且调研总管不得忽略 high 严重度问题
    并且飞书展示的候选状态应反映红队结果

  场景: 在飞书批准门铃包裹场景进入 Demo
    假如项目正在等待候选场景审批
    而且 Package Risk Intelligence 已通过自动门禁和红队检查
    当用户通过飞书提交 approve 并选中该 Innovation
    那么后端应记录操作者、理由和 Checkpoint
    并且项目应进入 demo_running
    并且重复提交相同决定不得重复启动 Demo

  场景: 运行 Package Risk Intelligence 多上下文判断
    假如系统收到包裹已送达且仍在门口的状态
    而且家庭当前无人
    而且天气数据表示预计降雨
    当 Demo 评估包裹风险
    那么结果应包含结构化 Inference、Risk 和 Action
    并且每个输入应记录来源、时间、置信度和模拟标记
    并且 LLM 不得单独决定风险等级

  场景: 上下文缺失时安全降级
    假如系统知道包裹仍在门口
    但是天气数据源不可用
    当 Demo 评估包裹风险
    那么结果应为 partial 或 inconclusive
    并且系统不得生成高置信度受损风险
    并且天气失败应保留在 Demo 结果和 Trace 中

  场景: 阻止无证据事实进入报告
    假如一个事实性 Claim 没有有效 Evidence ID
    当 Claim Gate 检查最终报告
    那么该 Claim 应被排除或标记为 missing_evidence
    并且排除原因应记录在项目 Trace

  场景: 从采集失败的 Checkpoint 恢复
    假如一个 Evidence 来源在研究阶段失败
    当操作员从保存的 Checkpoint 重试
    那么已经通过质量检查的无关阶段不应重复执行
    并且失败来源仍应显示在覆盖率指标中

  场景: 输出不建议立项
    假如用户痛点证据不足或候选存在未解决的 high 风险
    当最终审批选择 reject
    那么项目应进入 rejected 而不是 completed
    并且报告应输出 do_not_recommend
    并且补研条件、淘汰理由和人工决定应保持可追溯
