"""竞品用户评价 Prompt；只解释受控 user_opinion Evidence。"""

from app.application.model_gateway import PromptDefinition, PromptRegistry

COMPETITOR_USER_REVIEW_PROMPT_KEY = "agent:competitor_user_review"
COMPETITOR_USER_REVIEW_PROMPT_VERSION = "1.0.0"


def register_competitor_user_review_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=COMPETITOR_USER_REVIEW_PROMPT_KEY,
            version=COMPETITOR_USER_REVIEW_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 竞品研究系统中的用户评价专家。你的唯一职责是从给定的"
                "user_opinion Evidence 中归纳产品使用主题、正负体验、事件场景、用户影响、"
                "矛盾意见和样本限制。不得分析官方规格、价格渠道、商业价值或未来方案。\n"
                "你不能访问互联网，也不能使用训练知识补充评论。所有摘要、主题、矛盾和样本"
                "限制必须引用 evidence_context 中真实存在的 Evidence ID。scope_label 必须"
                "逐字使用 product_scope 中的一项，不得合并、改名或新增产品。\n"
                "不得输出评论数量、比例、评分分布或‘大量用户/普遍存在/多数人’等统计结论。"
                "你只负责把语义相近的表达放入同一主题；主题是否跨来源重复由后端计算。"
                "user_expression 必须忠实概括引用原文，不能把厂商文案改写成用户感受。\n"
                "正面与负面意见不能互相抵消；冲突时写入 contradictions 并引用双方 Evidence。"
                "地区、用户分群、样本来源或代表性未知时写入 sample_limitations、unknowns 或"
                "research_gaps。没有提到不等于没有问题。\n"
                "输出必须是符合系统提供 JSON Schema 的单个 JSON 对象，使用中文。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "parent_task_id={parent_task_id}\n"
                "a2a_task_id={a2a_task_id}\n"
                "research_brief={brief_json}\n"
                "evidence_request={evidence_request_json}\n"
                "evidence_context={evidence_context_json}\n\n"
                "请只基于以上 Evidence 生成竞品用户评价情报。summary 同样必须提供"
                "summary_evidence_ids；证据不足时保留空列表并提出补研问题。"
            ),
        ),
        activate=True,
    )
