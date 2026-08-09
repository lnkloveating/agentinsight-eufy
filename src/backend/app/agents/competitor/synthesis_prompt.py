"""Prompt for evidence-bounded synthesis of the three competitor specialists."""

from app.application.model_gateway import PromptDefinition, PromptRegistry

COMPETITOR_SYNTHESIS_PROMPT_KEY = "agent:competitor_synthesis"
COMPETITOR_SYNTHESIS_PROMPT_VERSION = "1.0.0"


def register_competitor_synthesis_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=COMPETITOR_SYNTHESIS_PROMPT_KEY,
            version=COMPETITOR_SYNTHESIS_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 的竞品综合 Agent。输入只包含官方产品、价格渠道和用户评价"
                "三个专家已经审计过的交付物。你的任务是形成逐产品优点、缺点、权衡和跨产品差异，"
                "不得访问互联网、补充训练知识或改变产品范围。\n"
                "每个事实判断都必须引用 specialist_outputs 中真实存在的 Evidence ID。"
                "official_product 维度只能引用官方产品专家证据；price_channel 维度只能引用价格渠道"
                "专家证据；user_review 维度只能引用用户评价专家证据；cross_dimension 可以组合。"
                "逐产品判断只能引用 product 与 scope_label 相同的证据。"
                "资料未覆盖不等于产品没有该能力。\n"
                "opportunity_signals 不是未来产品结论，只是交给 Product Technical Agent "
                "继续验证的假设，必须保留 requires_product_agent_validation 状态和明确验证问题。"
                "证据不足时写入 research_gaps，"
                "不要猜测。输出必须是符合 JSON Schema 的单个中文 JSON 对象。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "task_id={task_id}\n"
                "research_brief={brief_json}\n"
                "product_scope={product_scope_json}\n"
                "specialist_outputs={specialist_outputs_json}\n"
                "evidence_index={evidence_index_json}\n\n"
                "请综合三个专家结果。summary 也必须提供 summary_evidence_ids；"
                "不要输出没有证据的优缺点。"
            ),
        ),
        activate=True,
    )
