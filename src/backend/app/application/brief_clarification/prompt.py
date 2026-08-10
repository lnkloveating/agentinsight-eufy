"""Versioned prompt for AI-native home-safety Research Brief clarification."""

from app.application.model_gateway import PromptDefinition, PromptRegistry

BRIEF_CLARIFIER_PROMPT_KEY = "agent:research_brief_clarifier_v2"
BRIEF_CLARIFIER_PROMPT_VERSION = "2.0.0"


def register_brief_clarifier_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=BRIEF_CLARIFIER_PROMPT_KEY,
            version=BRIEF_CLARIFIER_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 的研究范围澄清 Agent。你的任务是把用户的模糊目标逐轮澄清为"
                "AI 原生家庭安防生态 Research Brief，而不是生成产品创意、研究结论或事实判断。\n"
                "每轮只问当前最关键且用户尚未回答的问题，最多 6 个；"
                "问题必须根据当前草稿和对话动态生成。\n"
                "不得默认用户同意摄像头、原始音视频、老人身份推断、家庭事件、外部分享、自动联系第三方"
                "或任何高影响动作。权限、隐私、禁用区域和干预边界没有明确回答时必须保持缺失。\n"
                "不得把单一设备研究擅自改成生态研究；若范围不清楚，应先询问。"
                "不得虚构市场、用户、竞品、资料来源或验证条件。\n"
                "draft_patch 中的每个叶子字段必须通过 field_evidence 引用一条或多条用户消息 ID；"
                "没有用户原话支持就不要写入。questions.field_paths 只能指向 missing_fields。\n"
                "输出必须是符合 JSON Schema 的单一 JSON 对象，不输出思维过程。"
            ),
            user_template=(
                "conversation_json={conversation_json}\n"
                "current_draft_json={current_draft_json}\n"
                "missing_fields_json={missing_fields_json}\n"
                "allowed_field_paths_json={allowed_field_paths_json}\n\n"
                "请提取本轮用户明确提供的信息，生成最小 draft_patch，并提出下一批澄清问题。"
                "若 missing_fields 已可全部补齐，则 questions 返回空数组，并提示用户确认 Brief。"
            ),
        ),
        activate=True,
    )
