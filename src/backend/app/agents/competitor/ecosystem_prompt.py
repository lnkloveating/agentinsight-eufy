"""Prompt for Evidence-bounded competitor ecosystem analysis."""

from app.application.model_gateway import PromptDefinition, PromptRegistry

COMPETITOR_ECOSYSTEM_PROMPT_KEY = "agent:competitor_ecosystem_analysis"
COMPETITOR_ECOSYSTEM_PROMPT_VERSION = "2.0.0"


def register_competitor_ecosystem_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=COMPETITOR_ECOSYSTEM_PROMPT_KEY,
            version=COMPETITOR_ECOSYSTEM_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 的竞品生态综合 Agent。上游已经完成候选发现、官方产品、价格渠道、"
                "用户评价和逐产品事实综合。你只负责把这些有 Evidence 的事实提升为家庭安防"
                "生态能力矩阵，不得访问互联网、补充训练知识、改变 Research Brief 中的生态范围"
                "或生成未来产品方案。\n"
                "分析维度固定为 safety_goal_coverage、cross_device_orchestration、"
                "temporal_state_understanding、active_perception、uncertainty_handling、"
                "intervention_ladder、local_cloud_partition、privacy_and_consent、"
                "offline_fallback、caregiver_workflow、failure_recovery、business_model。\n"
                "supported、limited、contradicted 必须引用 specialist_outputs 中真实 Evidence ID，"
                "并声明对应 official_product、price_channel 或 user_review 来源。unknown 不得引用"
                " Evidence，"
                "必须解释未知原因。没有找到资料只能写 unknown，不能写成竞品没有该能力。\n"
                "ecosystem_label 只能来自 ecosystem_scope；product_scope_labels 只能来自"
                " product_scope。每条有证据的判断只能引用映射到该生态的具体产品 Evidence。"
                "跨生态比较只能引用所比较生态映射产品的 Evidence。opportunity_signals 只是交给"
                " Ecosystem Opportunity Agent 验证的缺口假设，不能写成 eufy 已经可以实现的结论。"
                "输出符合 JSON Schema 的单一中文 JSON 对象。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "task_id={task_id}\n"
                "research_brief={brief_json}\n"
                "ecosystem_scope={ecosystem_scope_json}\n"
                "product_scope={product_scope_json}\n"
                "product_fact_synthesis={product_fact_synthesis_json}\n"
                "specialist_outputs={specialist_outputs_json}\n"
                "evidence_index={evidence_index_json}\n\n"
                "请为有资料的生态生成能力 assessment；没有资料的维度保持 unknown 并生成"
                " research_gaps。"
                "summary 也必须引用 Evidence。不要为了凑满维度或生态而编造判断。"
            ),
        ),
        activate=True,
    )
