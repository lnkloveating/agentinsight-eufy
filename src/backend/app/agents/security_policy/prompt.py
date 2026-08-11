"""Prompt registration for model-authored policy intent."""

from app.application.model_gateway import PromptDefinition, PromptRegistry

SECURITY_POLICY_PROMPT_KEY = "agent:security_policy_compiler"
SECURITY_POLICY_PROMPT_VERSION = "1.0.0"


def register_security_policy_prompt(registry: PromptRegistry) -> None:
    registry.register(
        PromptDefinition(
            prompt_key=SECURITY_POLICY_PROMPT_KEY,
            version=SECURITY_POLICY_PROMPT_VERSION,
            system_template=(
                "你是 AgentInsight 的安全策略意图设计 Agent。你只为已经通过技术可行性验证的 AI 原生"
                "家庭安防生态机会提出结构化策略意图，不生成可直接执行的设备命令。后端 Compiler 会"
                "生成规范 DSL、ID、版本、fallback、invariant、hash 和最终 compilation_status。\n"
                "只能使用 Research Brief 的 authorized_signal_types 和 allowed_interventions，"
                "只能引用生态机会中已有的 device role。不得请求原始媒体、绕过受限区域、"
                "进行 forbidden inference、"
                "修改权限、开锁、报警、联系未授权人员或执行任何未列出的动作。notify_authorized_contact"
                "和 preserve_evidence 必须 human_approval_required=true。\n"
                "每条风险规则必须引用 evidence_index 内真实 Evidence ID。证据或技术条件不足时写入"
                "assumptions/compilation_gaps，不得猜测设备、API 或家庭状态。"
                "策略必须维护跨时间状态，显式处理不确定性，并给出从低风险观察到高风险人工审批的"
                "干预阶梯。输出符合 JSON Schema"
                "的单个中文 JSON 对象。"
            ),
            user_template=(
                "project_id={project_id}\n"
                "task_id={task_id}\n"
                "selected_opportunity_ids={selected_opportunity_ids_json}\n"
                "research_brief={brief_json}\n"
                "ecosystem_opportunity={opportunity_json}\n"
                "technical_feasibility={technical_json}\n"
                "evidence_index={evidence_index_json}\n"
                "human_decision_history={decision_history_json}\n\n"
                "为每个 selected opportunity 生成一条 policy intent。"
                "state_variables 表达持续家庭状态；"
                "signal_requests 只表达授权元数据请求；risk_rules 必须引用已声明 state/signal；"
                "intervention_ladder 只能使用允许动作。"
                "不要输出 fallback、invariant、policy_id、版本、"
                "DSL hash、编译状态或真实执行结果，这些由后端确定性生成。"
            ),
        ),
        activate=True,
    )
