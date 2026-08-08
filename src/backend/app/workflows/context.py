"""按 Agent 职责构建最小必要上下文。"""

from app.schemas.project import ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchState,
    StageDecision,
)

CONTEXT_POLICY: dict[ResearchAgentType, set[ResearchAgentType]] = {
    ResearchAgentType.RESEARCH_MANAGER: set(),
    ResearchAgentType.USER_RESEARCH: set(),
    ResearchAgentType.COMPETITOR_RESEARCH: set(),
    ResearchAgentType.PRODUCT_TECHNICAL: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
    },
    ResearchAgentType.COMMERCIAL_EVALUATION: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
        ResearchAgentType.PRODUCT_TECHNICAL,
    },
    ResearchAgentType.RED_TEAM: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
        ResearchAgentType.PRODUCT_TECHNICAL,
        ResearchAgentType.COMMERCIAL_EVALUATION,
    },
    ResearchAgentType.CANDIDATE_SYNTHESIS: {
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
        ResearchAgentType.PRODUCT_TECHNICAL,
        ResearchAgentType.COMMERCIAL_EVALUATION,
        ResearchAgentType.RED_TEAM,
    },
    ResearchAgentType.VALIDATION: {
        ResearchAgentType.PRODUCT_TECHNICAL,
        ResearchAgentType.COMMERCIAL_EVALUATION,
        ResearchAgentType.RED_TEAM,
        ResearchAgentType.CANDIDATE_SYNTHESIS,
    },
    ResearchAgentType.FINAL_SYNTHESIS: set(ResearchAgentType),
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
    return AgentContext(
        project_id=state["project_id"],
        brief=ResearchBrief.model_validate(state["brief"]),
        iteration=state.get("iteration", 0),
        upstream_artifacts=artifacts,
        selected_innovation_ids=state.get("selected_innovation_ids", []),
        decision_history=decisions,
    )
