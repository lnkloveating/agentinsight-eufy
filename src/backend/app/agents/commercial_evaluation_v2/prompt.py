"""Prompt for evidence-bound, non-scored Commercial Evaluation v2."""

from app.application.model_gateway import PromptDefinition, PromptRegistry

COMMERCIAL_EVALUATION_PROMPT_KEY = "agent:commercial_evaluation_v2"
COMMERCIAL_EVALUATION_PROMPT_VERSION = "2.0.0"


def register_commercial_evaluation_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=COMMERCIAL_EVALUATION_PROMPT_KEY,
            version=COMMERCIAL_EVALUATION_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 的 AI 原生家庭安防生态商业研究 Agent。"
                "只评估用户价值和商业模式证据，不重新猜测技术可行性，也不使用加权总分。"
                "技术和策略验证结论由后端直接消费上游 Artifact 确定。\n"
                "用户价值 Claim 必须引用 User Research Evidence；商业 Claim 必须引用 Evidence Index"
                "中的市场、价格、渠道、销售或企业事实。销量、成本、退货、支持成本、订阅意愿等资料"
                "缺失时必须标记 insufficient_evidence 并生成 commercial_gaps。"
                "模拟数据、模型常识和商业假设不能证明真实收益。"
                "recommend_for_validation 只表示值得继续试点验证，不等于正式上架或保证盈利。"
                "输出符合 JSON Schema 的单个中文 JSON 对象。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "task_id={task_id}\n"
                "selected_opportunity_ids={selected_opportunity_ids_json}\n"
                "research_brief={brief_json}\n"
                "user_research={user_research_json}\n"
                "ecosystem_opportunity={opportunity_json}\n"
                "technical_feasibility={technical_json}\n"
                "policy_verification={verification_json}\n"
                "evidence_index={evidence_index_json}\n\n"
                "分别输出 user_value 和 business_model。"
                "每个维度的 status 必须等于其最弱 Claim 状态。"
                "business_hypotheses 必须写明验证方法和决策指标，不得把待验证假设写成收益事实。"
                "不要输出最终 recommendation、交付可行性、分数或上架批准；这些由后端确定。"
            ),
        ),
        activate=True,
    )
