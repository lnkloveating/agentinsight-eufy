"""不依赖 LLM 的 Artifact、红队和人工决定门禁。"""

from collections.abc import Iterable

from app.schemas.project import DecisionAction
from app.workflows.contracts import (
    EvidenceGateResult,
    GateName,
    GateRequest,
    RedTeamDirective,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTaskStatus,
    StageDecision,
    WorkflowContractError,
)

GATE_ACTIONS: dict[GateName, list[DecisionAction]] = {
    GateName.BRIEF: [
        DecisionAction.APPROVE,
        DecisionAction.REVISE,
        DecisionAction.TERMINATE,
    ],
    GateName.SCENARIO: [
        DecisionAction.APPROVE,
        DecisionAction.RESEARCH_MORE,
        DecisionAction.REVISE,
        DecisionAction.REJECT,
        DecisionAction.TERMINATE,
    ],
    GateName.FINAL: [
        DecisionAction.APPROVE,
        DecisionAction.RESEARCH_MORE,
        DecisionAction.REVISE,
        DecisionAction.REJECT,
        DecisionAction.TERMINATE,
    ],
}


def build_gate_request(
    project_id: str,
    gate: GateName,
    iteration: int,
    summary: dict[str, object],
) -> GateRequest:
    return GateRequest(
        decision_id=f"decision_{project_id}_{gate}_{iteration}",
        gate=gate,
        allowed_actions=GATE_ACTIONS[gate],
        project_id=project_id,
        checkpoint_hint=f"{project_id}:{gate}:{iteration}",
        summary=summary,
    )


def validate_stage_decision(raw: object, request: GateRequest) -> StageDecision:
    decision = StageDecision.model_validate(raw)
    if decision.decision_id != request.decision_id:
        raise WorkflowContractError("decision id does not match the pending gate")
    if decision.gate is not request.gate:
        raise WorkflowContractError("decision gate does not match the pending gate")
    if decision.action not in request.allowed_actions:
        raise WorkflowContractError("decision action is not allowed at this gate")
    if (
        request.gate is GateName.SCENARIO
        and decision.action is DecisionAction.APPROVE
        and not decision.selected_innovation_ids
    ):
        raise WorkflowContractError("scenario approval must select at least one innovation")
    return decision


def evaluate_research_artifacts(
    artifacts: dict[str, ResearchArtifact],
) -> EvidenceGateResult:
    """只检查 Artifact 就绪性；Evidence 的真实性仍由 Evidence/Claim Gate 负责。"""

    issues: list[str] = []
    for agent_type in (
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
    ):
        artifact = artifacts.get(agent_type.value)
        if artifact is None:
            issues.append(f"missing_artifact:{agent_type}")
            continue
        if artifact.status is not ResearchTaskStatus.COMPLETED:
            issues.append(f"artifact_not_completed:{agent_type}:{artifact.status}")
        if not artifact.evidence_ids:
            issues.append(f"artifact_has_no_evidence:{agent_type}")
    return EvidenceGateResult(passed=not issues, issues=issues)


def parse_red_team_directive(artifact: ResearchArtifact) -> RedTeamDirective:
    raw = artifact.payload.get("directive")
    if not isinstance(raw, dict):
        raise WorkflowContractError("red-team artifact must contain a directive object")
    return RedTeamDirective.model_validate(raw)


def summarize_artifacts(
    artifacts: Iterable[ResearchArtifact],
) -> dict[str, object]:
    items = list(artifacts)
    return {
        "artifact_ids": [artifact.artifact_id for artifact in items],
        "evidence_ids": sorted(
            {evidence_id for artifact in items for evidence_id in artifact.evidence_ids}
        ),
        "unknowns": [unknown for artifact in items for unknown in artifact.unknowns],
    }
