from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agents.ecosystem_opportunity import EcosystemOpportunityOutputValidator
from app.agents.technical_feasibility import (
    TechnicalFeasibilityModelOutput,
    TechnicalFeasibilityOutputValidator,
    TechnicalFeasibilityValidationError,
    TechnicalFeasibilityVerdict,
)
from app.core.config import Settings
from app.main import create_app
from app.workflows.contracts import (
    AgentContext,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)
from tests.unit.test_ecosystem_opportunity_agent import (
    _candidate,
    _graph,
)
from tests.unit.test_ecosystem_opportunity_agent import (
    _context as ecosystem_context,
)
from tests.unit.test_ecosystem_opportunity_agent import (
    _output as ecosystem_output,
)
from tests.unit.test_ecosystem_opportunity_agent import (
    _task as ecosystem_task,
)


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_technical_feasibility",
        project_id="proj_ecosystem",
        agent_type=ResearchAgentType.TECHNICAL_FEASIBILITY,
        goal="验证所选生态机会的 Demo 技术边界",
        budget=ResearchBudget(deadline_seconds=180),
    )


def _source(capability: str = "本地事件推理"):
    return EcosystemOpportunityOutputValidator().validate(
        ecosystem_task(),
        ecosystem_context(),
        _graph(),
        ecosystem_output([_candidate(1, capability)]),
    )


def _context(capability: str = "本地事件推理") -> AgentContext:
    source = _source(capability)
    return AgentContext(
        project_id="proj_ecosystem",
        brief=ecosystem_context().brief,
        iteration=0,
        upstream_artifacts={
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: source,
        },
        selected_innovation_ids=["eco_dynamic_1"],
        evidence_context=AgentEvidenceContext(
            items=[],
            available_evidence_count=0,
            included_evidence_count=0,
            omitted_evidence_count=0,
            context_hash="d" * 64,
        ),
        research_handoff=ecosystem_context().research_handoff,
    )


def _model_output(*, evidence_id: str = "ev_device") -> TechnicalFeasibilityModelOutput:
    requirements = [
        {
            "requirement_id": f"req_{kind}",
            "kind": kind,
            "description": f"验证 {kind} 技术条件",
            "status": "supported",
            "rationale": "已有受控技术证据。",
            "evidence_ids": [evidence_id],
        }
        for kind in ("data", "deployment", "performance", "privacy", "resilience")
    ]
    return TechnicalFeasibilityModelOutput.model_validate(
        {
            "summary": "所选机会已完成技术需求分解。",
            "summary_evidence_ids": [evidence_id],
            "assessments": [
                {
                    "opportunity_id": "eco_dynamic_1",
                    "architecture_summary": "设备感知、HomeBase 推理和受控通知。",
                    "requirements": requirements,
                    "demo_scope": "使用授权或模拟事件验证受限策略。",
                    "limitations": ["不作医疗诊断。"],
                    "failure_modes": ["设备离线时上下文不完整。"],
                    "source_requirements": [],
                }
            ],
            "portfolio_gaps": [],
            "unknowns": [],
        }
    )


def _fully_supported_graph():
    graph = _graph()
    facts = [
        item.model_copy(
            update={
                "authorization_required": False,
                "offline_support": "full",
            }
        )
        for item in graph.facts
    ]
    return graph.model_copy(update={"facts": facts})


def test_backend_computes_demo_feasible_for_supported_capabilities() -> None:
    artifact = TechnicalFeasibilityOutputValidator().validate(
        _task(),
        _context(),
        _fully_supported_graph(),
        _model_output(),
    )

    assessment = artifact.payload.assessments[0]
    assert assessment.verdict is TechnicalFeasibilityVerdict.DEMO_FEASIBLE
    assert artifact.payload.coverage.demo_feasible_count == 1
    assert artifact.payload.coverage.insufficient_evidence_count == 0


def test_authorization_or_degraded_offline_support_is_conditional() -> None:
    artifact = TechnicalFeasibilityOutputValidator().validate(
        _task(),
        _context(),
        _graph(),
        _model_output(),
    )

    assert (
        artifact.payload.assessments[0].verdict
        is TechnicalFeasibilityVerdict.CONDITIONALLY_FEASIBLE
    )


def test_missing_device_capability_creates_source_recovery_gap() -> None:
    capability = "跨房间异常行为基线"
    artifact = TechnicalFeasibilityOutputValidator().validate(
        _task(),
        _context(capability),
        _fully_supported_graph(),
        _model_output(),
    )

    assessment = artifact.payload.assessments[0]
    assert assessment.verdict is TechnicalFeasibilityVerdict.INSUFFICIENT_EVIDENCE
    assert any(capability in gap.question for gap in assessment.source_requirements)


def test_explicitly_unsupported_capability_blocks_feasibility() -> None:
    graph = _fully_supported_graph()
    facts = [
        item.model_copy(update={"assertion": "unsupported", "availability": "unavailable"})
        for item in graph.facts
    ]
    artifact = TechnicalFeasibilityOutputValidator().validate(
        _task(),
        _context(),
        graph.model_copy(update={"facts": facts}),
        _model_output(),
    )

    assert (
        artifact.payload.assessments[0].verdict
        is TechnicalFeasibilityVerdict.NOT_FEASIBLE
    )


def test_hallucinated_evidence_is_rejected() -> None:
    with pytest.raises(
        TechnicalFeasibilityValidationError,
        match="outside the bounded context",
    ):
        TechnicalFeasibilityOutputValidator().validate(
            _task(),
            _context(),
            _fully_supported_graph(),
            _model_output(evidence_id="ev_fake"),
        )


def test_model_output_cannot_set_backend_verdict() -> None:
    raw = deepcopy(_model_output().model_dump(mode="json"))
    raw["assessments"][0]["verdict"] = "demo_feasible"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TechnicalFeasibilityModelOutput.model_validate(raw)


def test_public_technical_feasibility_routes_are_registered() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]

    assert "/api/v1/projects/{project_id}/agents/technical-feasibility" in paths
    assert (
        "/api/v1/projects/{project_id}/agents/technical-feasibility/artifacts"
        in paths
    )
