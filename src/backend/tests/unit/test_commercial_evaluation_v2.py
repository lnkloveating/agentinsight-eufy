from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.agents.commercial_evaluation_v2 import (
    CommercialConclusionStatus,
    CommercialEvaluationModelOutput,
    CommercialEvaluationOutputValidator,
    CommercialEvaluationValidationError,
    CommercialRecommendation,
)
from app.agents.policy_verification import (
    PolicyVerificationRunCreate,
    SecurityPolicyVerificationEngine,
)
from app.agents.security_policy import SecurityPolicyCompiler
from app.agents.technical_feasibility import TechnicalFeasibilityOutputValidator
from app.agents.user_research.validation import UserResearchOutputValidator
from app.application.source_recovery.gaps import AgentGapProjector
from app.core.config import Settings
from app.main import create_app
from app.schemas.source_recovery import RecoverableAgentType
from app.workflows.contracts import (
    AgentContext,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
)
from tests.unit.test_policy_verification import _task as verification_task
from tests.unit.test_security_policy_compiler import _output as policy_output
from tests.unit.test_security_policy_compiler import _task as policy_task
from tests.unit.test_technical_feasibility_agent import (
    _context as technical_context,
)
from tests.unit.test_technical_feasibility_agent import (
    _fully_supported_graph,
)
from tests.unit.test_technical_feasibility_agent import (
    _model_output as technical_output,
)
from tests.unit.test_technical_feasibility_agent import _task as technical_task
from tests.unit.test_user_research_contracts import (
    _agent_evidence,
)
from tests.unit.test_user_research_contracts import (
    _complete_output as user_output,
)
from tests.unit.test_user_research_contracts import (
    _task as user_task,
)


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_commercial_evaluation_v2",
        project_id="proj_ecosystem",
        agent_type=ResearchAgentType.COMMERCIAL_EVALUATION,
        goal="Decide whether an ecosystem opportunity warrants further validation.",
        budget=ResearchBudget(deadline_seconds=180),
    )


def _context() -> AgentContext:
    base = technical_context()
    opportunity = base.upstream_artifacts[
        ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value
    ]
    technical = TechnicalFeasibilityOutputValidator().validate(
        technical_task(), base, _fully_supported_graph(), technical_output()
    )
    policy_context = AgentContext(
        project_id=base.project_id,
        brief=base.brief,
        iteration=0,
        upstream_artifacts={
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: opportunity,
            ResearchAgentType.TECHNICAL_FEASIBILITY.value: (
                technical.to_research_artifact()
            ),
        },
        selected_innovation_ids=["eco_dynamic_1"],
        evidence_context=base.evidence_context,
        research_handoff=base.research_handoff,
    )
    policy = SecurityPolicyCompiler().compile(
        policy_task(), policy_context, policy_output()
    )
    verification = SecurityPolicyVerificationEngine().verify(
        verification_task(), policy, PolicyVerificationRunCreate()
    )
    evidence_context = AgentEvidenceContext(
        items=[
            _agent_evidence("ev_one", domain="reviews.example"),
            _agent_evidence("ev_two", domain="community.example"),
            _agent_evidence(
                "ev_market",
                domain="market.example",
                claim_type="market_fact",
            ),
            _agent_evidence(
                "ev_device",
                domain="vendor.example",
                claim_type="technical_fact",
            ),
        ],
        available_evidence_count=4,
        included_evidence_count=4,
        omitted_evidence_count=0,
        context_hash="e" * 64,
    )
    user = UserResearchOutputValidator().validate(
        user_task(),
        AgentEvidenceContext(
            items=evidence_context.items[:2],
            available_evidence_count=2,
            included_evidence_count=2,
            omitted_evidence_count=0,
            context_hash="a" * 64,
        ),
        user_output(),
    )
    return AgentContext(
        project_id=base.project_id,
        brief=base.brief,
        iteration=0,
        upstream_artifacts={
            ResearchAgentType.USER_RESEARCH.value: user,
            ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value: opportunity,
            ResearchAgentType.TECHNICAL_FEASIBILITY.value: (
                technical.to_research_artifact()
            ),
            ResearchAgentType.POLICY_VERIFICATION.value: (
                verification.to_research_artifact()
            ),
        },
        selected_innovation_ids=["eco_dynamic_1"],
        evidence_context=evidence_context,
        research_handoff=base.research_handoff,
    )


def _output(
    *,
    user_status: str = "supported",
    business_status: str = "supported",
    business_evidence_id: str = "ev_market",
    include_gap: bool = False,
) -> CommercialEvaluationModelOutput:
    raw: dict[str, object] = {
        "summary": "用户价值与商业假设已分别评估。",
        "summary_evidence_ids": ["ev_one", "ev_market"],
        "user_value": {
            "status": user_status,
            "conclusion": "用户需要减少对每条安防通知的手工解释。",
            "claims": [
                {
                    "claim": "用户仍需手工判断通知是否需要处理。",
                    "status": user_status,
                    "rationale": "两个独立用户来源描述了相同工作负担。",
                    "evidence_ids": ["ev_one", "ev_two"],
                }
            ],
            "assumptions": [],
        },
        "business_model": {
            "status": business_status,
            "conclusion": "该能力存在值得验证的服务假设。",
            "claims": [
                {
                    "claim": "现有渠道事实支持开展受控付费意愿验证。",
                    "status": business_status,
                    "rationale": "这里只形成假设，不保证实际收入。",
                    "evidence_ids": [business_evidence_id],
                }
            ],
            "assumptions": ["企业内部成本仍需验证"],
        },
        "business_hypotheses": [
            {
                "hypothesis": "用户可能愿意为持续状态理解付费。",
                "validation_method": "开展受控概念测试与价格敏感度访谈。",
                "decision_metric": "目标用户的试点转化意向达到预设门槛。",
                "evidence_ids": [business_evidence_id],
            }
        ],
        "commercial_gaps": [],
        "unknowns": [],
    }
    if include_gap:
        raw["commercial_gaps"] = [
            {
                "dimension": "willingness_to_pay",
                "question": "目标照护家庭的付费意愿区间是多少？",
                "reason": "公开资料不能证明真实转化。",
                "affected_opportunity_ids": ["eco_dynamic_1"],
                "recommended_source_types": ["enterprise_data", "user_interview"],
            }
        ]
    return CommercialEvaluationModelOutput.model_validate(raw)


def test_backend_recommends_validation_without_commercial_score() -> None:
    artifact = CommercialEvaluationOutputValidator().validate(
        _task(), _context(), _output()
    )

    assert (
        artifact.payload.recommendation
        is CommercialRecommendation.RECOMMEND_FOR_VALIDATION
    )
    assert artifact.payload.delivery_operations.status is CommercialConclusionStatus.SUPPORTED
    assert "上架" in artifact.payload.recommendation_reason
    assert "weighted_score" not in artifact.payload.model_dump(mode="json")


def test_unsupported_dimension_is_deterministically_not_recommended() -> None:
    artifact = CommercialEvaluationOutputValidator().validate(
        _task(), _context(), _output(business_status="unsupported")
    )

    assert artifact.payload.recommendation is CommercialRecommendation.DO_NOT_RECOMMEND


def test_insufficient_evidence_requires_recovery_gap_and_projects_scope() -> None:
    validator = CommercialEvaluationOutputValidator()
    with pytest.raises(
        CommercialEvaluationValidationError,
        match="require explicit recovery gaps",
    ):
        validator.validate(
            _task(),
            _context(),
            _output(business_status="insufficient_evidence"),
        )

    artifact = validator.validate(
        _task(),
        _context(),
        _output(business_status="insufficient_evidence", include_gap=True),
    )
    projected = AgentGapProjector().project(
        artifact.to_research_artifact(),
        RecoverableAgentType.COMMERCIAL_EVALUATION,
    )
    assert artifact.payload.recommendation is CommercialRecommendation.NEEDS_MORE_EVIDENCE
    assert projected[0].affected_candidate_ids == ["eco_dynamic_1"]


def test_user_and_business_claims_enforce_distinct_evidence_types() -> None:
    raw = deepcopy(_output().model_dump(mode="json"))
    raw["user_value"]["claims"][0]["evidence_ids"] = ["ev_market"]
    with pytest.raises(CommercialEvaluationValidationError, match="User Research"):
        CommercialEvaluationOutputValidator().validate(
            _task(),
            _context(),
            CommercialEvaluationModelOutput.model_validate(raw),
        )

    with pytest.raises(CommercialEvaluationValidationError, match="Business claims"):
        CommercialEvaluationOutputValidator().validate(
            _task(),
            _context(),
            _output(business_evidence_id="ev_one"),
        )


def test_hallucinated_evidence_is_rejected() -> None:
    with pytest.raises(
        CommercialEvaluationValidationError,
        match="outside the bounded context",
    ):
        CommercialEvaluationOutputValidator().validate(
            _task(),
            _context(),
            _output(business_evidence_id="ev_fake"),
        )


def test_model_cannot_set_recommendation_delivery_or_score() -> None:
    for field, value in (
        ("recommendation", "recommend_for_validation"),
        ("delivery_operations", {"status": "supported"}),
        ("weighted_score", 100),
    ):
        raw = deepcopy(_output().model_dump(mode="json"))
        raw[field] = value
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CommercialEvaluationModelOutput.model_validate(raw)


def test_public_routes_and_checked_in_openapi_expose_v2_contract() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    route = "/api/v1/projects/{project_id}/agents/commercial-evaluation-v2"
    assert route in paths
    assert f"{route}/artifacts" in paths

    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )
    schema = document["paths"][
        "/projects/{project_id}/agents/commercial-evaluation-v2"
    ]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/CommercialEvaluationRunCreate"}
    assert set(
        document["components"]["schemas"]["CommercialRecommendation"]["enum"]
    ) == {item.value for item in CommercialRecommendation}
