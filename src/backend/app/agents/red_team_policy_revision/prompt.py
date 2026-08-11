"""Prompt for evidence-bound Red Team Policy Revision v2."""

from app.application.model_gateway import PromptDefinition, PromptRegistry

RED_TEAM_PROMPT_KEY = "agent:red_team_policy_revision"
RED_TEAM_PROMPT_VERSION = "2.0.0"


def register_red_team_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=RED_TEAM_PROMPT_KEY,
            version=RED_TEAM_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 的 AI 原生家庭安防红队。你的任务不是重复总结，也不是替方案辩护，"
                "而是使用给定 Artifact 和 Evidence 主动寻找证据越界、技术不可行、"
                "安全失败、隐私授权、"
                "误报漏报、离线降级、干预权限、商业夸大和伪 AI 原生问题。"
                "每个事实性 Finding 必须引用 Evidence Index 中的 Evidence ID，"
                "并且只能引用当前 Artifact、Opportunity、Policy 和 Scenario ID。"
                "资料不足必须生成 red_team_gaps；涉及隐私同意或高风险动作必须标记 "
                "requires_human_decision；只有确实不可通过缩小范围或修订解决的 "
                "critical 问题才能标记 irreducible。你不能输出最终 verdict、任务 ID、"
                "RevisionRequest、分数或部署批准，"
                "这些由后端确定性计算。输出符合 JSON Schema 的单个中文 JSON 对象。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "task_id={task_id}\n"
                "research_brief={brief_json}\n"
                "selected_opportunity_ids={selected_opportunity_ids_json}\n"
                "user_challenges={challenges_json}\n"
                "user_research={user_research_json}\n"
                "competitor_ecosystem={competitor_json}\n"
                "ecosystem_opportunity={opportunity_json}\n"
                "technical_feasibility={technical_json}\n"
                "security_policy={policy_json}\n"
                "policy_verification={verification_json}\n"
                "commercial_evaluation={commercial_json}\n"
                "previous_red_team={previous_red_team_json}\n"
                "evidence_index={evidence_index_json}\n\n"
                "必须覆盖九个自动攻击维度；存在用户质疑时还必须覆盖 user_challenge。"
                "每个用户质疑必须按 challenge_id 返回一次 response，"
                "无法回答时明确 unresolved 并生成补研缺口。"
                "不要因为方案被否决而输出空结果：可能不可修复时提供范围更小、"
                "动作更安全的 fallback_plan。"
            ),
        ),
        activate=True,
    )
