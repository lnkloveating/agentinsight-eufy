"""不依赖 LLM 的 Artifact、红队和人工决定门禁。"""

from collections.abc import Iterable

from app.schemas.project import DecisionAction
from app.workflows.contracts import (
    EvidenceGateResult,
    GateName,
    GateRequest,
    RedTeamDirective,
    ResearchArtifact,
    StageDecision,
    WorkflowContractError,
)
from app.workflows.handoff import build_research_handoff

GATE_ACTIONS: dict[GateName, list[DecisionAction]] = {
    GateName.BRIEF: [
        DecisionAction.APPROVE,
        DecisionAction.REVISE,
        DecisionAction.TERMINATE,
    ],
    GateName.AI_NATIVE_ECOSYSTEM: [
        DecisionAction.APPROVE,
        DecisionAction.RESEARCH_MORE,
        DecisionAction.REVISE,
        DecisionAction.REJECT,
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
    allowed_actions = list(GATE_ACTIONS[gate])
    if gate is GateName.AI_NATIVE_ECOSYSTEM:
        if not summary.get("eligible_opportunity_ids"):
            allowed_actions.remove(DecisionAction.APPROVE)
        if not summary.get("source_recovery_gap_ids"):
            allowed_actions.remove(DecisionAction.RESEARCH_MORE)
    return GateRequest(
        decision_id=f"decision_{project_id}_{gate}_{iteration}",
        gate=gate,
        allowed_actions=allowed_actions,
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
        request.gate in {GateName.SCENARIO, GateName.AI_NATIVE_ECOSYSTEM}
        and decision.action is DecisionAction.APPROVE
        and not decision.selected_innovation_ids
    ):
        raise WorkflowContractError("approval must select at least one opportunity")
    if len(decision.selected_innovation_ids) != len(set(decision.selected_innovation_ids)):
        raise WorkflowContractError("selected opportunity ids must be unique")
    if (
        request.gate is GateName.AI_NATIVE_ECOSYSTEM
        and decision.action is DecisionAction.APPROVE
    ):
        eligible = {
            str(item) for item in request.summary.get("eligible_opportunity_ids", [])
        }
        unsupported = sorted(set(decision.selected_innovation_ids) - eligible)
        if unsupported:
            raise WorkflowContractError(
                f"selected opportunities did not pass AI-native checks: {unsupported}"
            )
    if (
        request.gate is GateName.AI_NATIVE_ECOSYSTEM
        and decision.action is DecisionAction.RESEARCH_MORE
        and not request.summary.get("source_recovery_gap_ids")
    ):
        raise WorkflowContractError("AI-native research_more requires source gaps")
    return decision


def evaluate_research_artifacts(
    artifacts: dict[str, ResearchArtifact],
) -> EvidenceGateResult:
    """判断并行研究结果能否形成产品技术阶段的强类型交接。"""

    handoff = build_research_handoff(artifacts)
    return EvidenceGateResult(
        passed=handoff.ready_for_product_technical,
        issues=handoff.issues,
    )


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
