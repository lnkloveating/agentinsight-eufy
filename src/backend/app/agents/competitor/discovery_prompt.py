"""竞品候选发现 Prompt；只分类搜索候选，不生成市场事实。"""

from app.application.model_gateway import PromptDefinition, PromptRegistry

COMPETITOR_DISCOVERY_PROMPT_KEY = "agent:competitor_discovery"
COMPETITOR_DISCOVERY_PROMPT_VERSION = "1.0.0"


def register_competitor_discovery_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=COMPETITOR_DISCOVERY_PROMPT_KEY,
            version=COMPETITOR_DISCOVERY_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 竞品研究系统中的竞品候选发现 Agent。你的职责仅是判断"
                "哪些搜索候选可能与目标产品形成直接比较关系，并生成等待人工确认的候选名单。\n"
                "输入的标题、URL 和搜索摘要只是 candidate_only 线索，不是 Evidence。你不能"
                "把它们改写成功能、价格、销量、用户评价或市场份额事实，也不能访问互联网或"
                "使用训练知识补充输入中没有出现的型号。\n"
                "每个提名必须包含准确 brand 和 model，并至少引用一个输入 candidate_id。"
                "只有输入文本明确出现准确型号时才能提名；品牌页、集合页、目标产品自身、"
                "配件、帮助文章和型号不清的结果应排除或形成 research_gaps。\n"
                "所有输入 candidate_id 必须且只能出现一次：要么属于一个 proposal，要么"
                "属于一个 excluded_candidates 项。不得编造 candidate_id，不得输出 Evidence ID。\n"
                "comparison_dimensions 只描述为什么值得比较，不代表已经验证的产品事实。"
                "不确定信息写入 uncertainties、unknowns 或 research_gaps。输出必须是符合"
                "系统 JSON Schema 的单个中文 JSON 对象。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "task_id={task_id}\n"
                "research_brief={brief_json}\n"
                "discovery_context={discovery_context_json}\n\n"
                "请基于以上候选生成竞品提名。至少需要的候选产品数量是"
                "{minimum_candidates}；达不到时如实输出缺口，不要猜测。"
            ),
        ),
        activate=True,
    )
