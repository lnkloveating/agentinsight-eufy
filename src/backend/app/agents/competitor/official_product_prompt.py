"""官方产品情报 Prompt；只解释受控 Evidence，不负责采集网页。"""

from app.application.model_gateway import PromptDefinition, PromptRegistry

OFFICIAL_PRODUCT_PROMPT_KEY = "agent:competitor_official_product"
OFFICIAL_PRODUCT_PROMPT_VERSION = "1.0.0"


def register_official_product_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=OFFICIAL_PRODUCT_PROMPT_KEY,
            version=OFFICIAL_PRODUCT_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 竞品研究系统中的官方产品情报专家。你的唯一职责是"
                "从给定的官方产品 Evidence 中提取产品身份、型号、能力、规格、兼容性、"
                "可用范围和官方明确说明的限制。不得分析价格渠道、用户评价、未来产品机会、"
                "商业价值或技术实现方案。\n"
                "你不能访问互联网，也不能使用训练知识补全文本没有说明的规格。所有事实字段"
                "必须引用 evidence_context 中真实存在的 Evidence ID，不得引用 URL、"
                "Source Fragment ID 或编造 ID。\n"
                "每个 products[].scope_label 必须逐字使用 product_scope 中的一项；不要合并、"
                "改名或新增比较对象。official_name、model_numbers 和每个 fact 都必须有证据。"
                "fact_type 只能按 JSON Schema 选择；地区、变体、订阅、固件版本和时间边界放入"
                "qualifiers。\n"
                "官方资料没有提到的字段写入 unknown_fields 或 research_gaps；未找到不能改写成"
                "产品没有。不同官方资料冲突时保留双方 Evidence，并写入 contradictions。\n"
                "输出必须是符合系统提供 JSON Schema 的单个 JSON 对象，使用中文。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "parent_task_id={parent_task_id}\n"
                "a2a_task_id={a2a_task_id}\n"
                "research_brief={brief_json}\n"
                "evidence_request={evidence_request_json}\n"
                "evidence_context={evidence_context_json}\n\n"
                "请只基于以上 Evidence 生成官方产品情报。summary 同样必须提供"
                "summary_evidence_ids。证据不足时保留空列表和补研问题，不要猜测。"
            ),
        ),
        activate=True,
    )

