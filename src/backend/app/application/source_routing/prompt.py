"""资料路由 Prompt；只分类资料用途，不提取或判断事实。"""

from app.application.model_gateway import PromptDefinition, PromptRegistry

SOURCE_ROUTING_PROMPT_KEY = "agent:source_routing"
SOURCE_ROUTING_PROMPT_VERSION = "1.0.0"


def register_source_routing_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=SOURCE_ROUTING_PROMPT_KEY,
            version=SOURCE_ROUTING_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 统一资料中心的路由分类器。你只判断给定资料适合分发给"
                "哪些研究 Agent，以及资料片段可能承载哪些允许的 Claim 类型。你不得提取"
                "价格、规格、用户结论或未来机会，不得把分类结果表述为事实验证。\n"
                "路由是多标签的：同一资料可以同时属于 official_product、price_channel、"
                "user_review、user_research、market_research、technical_document、"
                "commercial_data、enterprise_internal 或 media_review。只使用 JSON Schema"
                "提供的枚举，不得新增标签。\n"
                "每条 suggestion 的 suggested_by 必须是 model。confidence 只表示分类置信度；"
                "reason 要说明可复核的文本或来源特征，signals 使用短标签。信息不足时返回"
                "空 suggestions 并写入 unknowns。输出必须是符合 Schema 的单个 JSON 对象。"
            ),
            user_template=(
                "project_brief={brief_json}\n"
                "source_metadata={source_metadata_json}\n"
                "deterministic_suggestions={rule_suggestions_json}\n"
                "bounded_fragments={fragment_context_json}\n\n"
                "请对资料进行多标签路由分类。确定性建议仅是辅助信号；不要复制其错误，"
                "也不要输出任何资料中没有的产品事实。"
            ),
        ),
        activate=True,
    )
