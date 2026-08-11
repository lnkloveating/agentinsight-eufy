"""按 Agent 职责构建最小必要上下文。"""

from app.schemas.project import ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchHandoff,
    ResearchState,
    StageDecision,
)

CONTEXT_POLICY: dict[ResearchAgentType, set[ResearchAgentType]] = {
    ResearchAgentType.RESEARCH_MANAGER: set(),
    ResearchAgentType.USER_RESEARCH: set(),
    ResearchAgentType.COMPETITOR_RESEARCH: set(),
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
    },
    ResearchAgentType.TECHNICAL_FEASIBILITY: {
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
    },
    ResearchAgentType.SECURITY_POLICY: {
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        ResearchAgentType.TECHNICAL_FEASIBILITY,
        ResearchAgentType.SECURITY_POLICY,
    },
    ResearchAgentType.POLICY_VERIFICATION: {
        ResearchAgentType.SECURITY_POLICY,
    },
    ResearchAgentType.COMMERCIAL_EVALUATION: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        ResearchAgentType.TECHNICAL_FEASIBILITY,
        ResearchAgentType.POLICY_VERIFICATION,
    },
    ResearchAgentType.RED_TEAM: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        ResearchAgentType.TECHNICAL_FEASIBILITY,
        ResearchAgentType.SECURITY_POLICY,
        ResearchAgentType.POLICY_VERIFICATION,
        ResearchAgentType.COMMERCIAL_EVALUATION,
    },
}


def build_agent_context(
    state: ResearchState,
    agent_type: ResearchAgentType,
) -> AgentContext:
    allowed = {item.value for item in CONTEXT_POLICY[agent_type]}
    artifacts = {
        key: ResearchArtifact.model_validate(value)
        for key, value in state.get("artifacts", {}).items()
        if key in allowed
    }
    decisions = [StageDecision.model_validate(item) for item in state.get("decision_history", [])]
    raw_handoff = state.get("research_handoff")
    handoff = (
        ResearchHandoff.model_validate(raw_handoff)
        if agent_type
        in {
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
            ResearchAgentType.TECHNICAL_FEASIBILITY,
            ResearchAgentType.SECURITY_POLICY,
            ResearchAgentType.COMMERCIAL_EVALUATION,
        }
        and raw_handoff is not None
        else None
    )
    return AgentContext(
        project_id=state["project_id"],
        brief=ResearchBrief.model_validate(state["brief"]),
        iteration=state.get("iteration", 0),
        upstream_artifacts=artifacts,
        selected_innovation_ids=state.get("selected_innovation_ids", []),
        decision_history=decisions,
        research_handoff=handoff,
    )
