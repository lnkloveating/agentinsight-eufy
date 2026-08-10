"""生态机会契约的确定性结构校验与新旧兼容性测试。"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.ecosystem_opportunity.contracts import (
    EcosystemBlueprint,
    EcosystemOpportunityArtifact,
    EcosystemOpportunityCandidate,
    EcosystemOpportunityCoverage,
    EcosystemOpportunityModelCandidate,
    EcosystemOpportunityModelOutput,
    EcosystemOpportunityPayload,
    SolutionScope,
    ecosystem_opportunity_gap_id,
)
from app.agents.product_technical.contracts import (
    ProductTechnicalArtifact,
    ProductTechnicalCoverage,
    ProductTechnicalPayload,
)
from app.schemas.source_recovery import RecoverableAgentType
from app.workflows.contracts import (
    ResearchAgentType,
    ResearchArtifact,
    ResearchHandoffStatus,
    ResearchTaskStatus,
)

_HASH = "a" * 64


def _blueprint() -> dict[str, Any]:
    return {
        "required_device_roles": [
            {
                "role_id": "r_cam",
                "role_type": "primary_perception",
                "description": "front door video doorbell",
                "required_capabilities": ["package_presence"],
                "optional": False,
                "evidence_ids": ["ev_user_1"],
            },
            {
                "role_id": "r_hub",
                "role_type": "local_reasoning_hub",
                "description": "homebase local reasoning",
                "required_capabilities": [],
                "optional": False,
                "evidence_ids": [],
            },
        ],
        "required_capabilities": ["package_presence", "person_identity"],
        "cross_device_information_flows": [
            {
                "flow_id": "flow_detection",
                "from_role_id": "r_cam",
                "to_role_id": "r_hub",
                "data_type": "detection_event",
                "purpose": "reason about unattended package",
                "privacy_constraints": ["local_only"],
                "fallback": "degrade to notification only",
            }
        ],
        "deployment_target": "hybrid",
        "privacy_boundary": "prefer local processing on homebase",
        "permission_boundary": "sensitive actions require human approval",
        "offline_behavior": "queue events and degrade gracefully",
        "fallback_behavior": "notify the user without autonomous action",
        "known_blind_spots": ["night low light identity"],
    }


def _ai_native_case() -> dict[str, Any]:
    return {
        "open_ended_goal": "protect doorstep packages when nobody is home",
        "why_fixed_rules_are_insufficient": "each home has different devices and habits",
        "model_responsibilities": ["interpret the open-ended safety goal"],
        "deterministic_responsibilities": ["enforce permissions and fallbacks"],
        "ai_removal_test": {
            "core_value_survives_without_ai": False,
            "rationale": "goal understanding and policy generation require AI",
            "lost_capabilities_without_ai": ["goal-to-policy compilation"],
            "evidence_ids": ["ev_user_1"],
        },
        "learning_or_revision_loop": ["revise policy after a failed scenario"],
        "safety_constraints": ["never auto unlock the door"],
    }


def _validation_plan() -> dict[str, Any]:
    return {
        "validation_goal": "verify the package protection policy before deployment",
        "required_scenario_types": ["normal", "adversarial"],
        "success_conditions": ["family pickup produces no alert"],
        "failure_conditions": ["stranger removal produces no alert"],
        "required_data": ["historical doorstep events"],
        "human_review_points": ["before enabling deployment"],
    }


def _model_candidate(
    scope: str = "ecosystem_service", opportunity_id: str = "eco_guard"
) -> dict[str, Any]:
    return {
        "opportunity_id": opportunity_id,
        "name": f"eufy Guardian Agent {opportunity_id}",
        "scope_level": scope,
        "target_user": {"persona_ids": ["persona_na_home"], "description": "north america homes"},
        "problem": {"pain_ids": ["pain_verify_theft"], "description": "hard to verify theft"},
        "safety_goal": "protect unattended doorstep packages",
        "ecosystem_blueprint": _blueprint(),
        "ai_native_case": _ai_native_case(),
        "competitor_gap_ids": ["gap_competitor_1"],
        "technical_hypotheses": ["reuse existing homebase for local reasoning"],
        "commercial_hypotheses": ["subscription for verified security policies"],
        "validation_plan": _validation_plan(),
        "evidence_ids": ["ev_user_1", "ev_comp_1"],
    }


def _coverage(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "generated_candidate_count": 1,
        "advancing_candidate_count": 1,
        "ecosystem_service_count": 1,
        "cited_user_evidence_count": 1,
        "cited_competitor_evidence_count": 1,
        "evidence_context_hash": _HASH,
        "handoff_status": "ready",
    }
    base.update(overrides)
    return base


# 1. 合法 ecosystem_service 候选可以解析。
def test_valid_ecosystem_service_candidate_parses() -> None:
    candidate = EcosystemOpportunityModelCandidate.model_validate(_model_candidate())
    assert candidate.scope_level is SolutionScope.ECOSYSTEM_SERVICE
    assert candidate.ecosystem_blueprint.deployment_target.value == "hybrid"


# 2. 合法 device_feature 候选可以解析。
def test_valid_device_feature_candidate_parses() -> None:
    candidate = EcosystemOpportunityModelCandidate.model_validate(
        _model_candidate(scope="device_feature")
    )
    assert candidate.scope_level is SolutionScope.DEVICE_FEATURE


# 3. 未知 scope_level 被拒绝。
def test_unknown_scope_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EcosystemOpportunityModelCandidate.model_validate(_model_candidate(scope="gadget"))


# 4. 重复 opportunity_id 被拒绝。
def test_duplicate_opportunity_id_is_rejected() -> None:
    output = {
        "summary": "two opportunities collide on id",
        "summary_evidence_ids": [],
        "opportunities": [
            _model_candidate(opportunity_id="same"),
            _model_candidate(opportunity_id="same"),
        ],
        "portfolio_gaps": [],
        "unknowns": [],
    }
    with pytest.raises(ValidationError):
        EcosystemOpportunityModelOutput.model_validate(output)


# 5. 重复 role_id 被拒绝。
def test_duplicate_role_id_is_rejected() -> None:
    blueprint = _blueprint()
    blueprint["required_device_roles"][1]["role_id"] = "r_cam"
    with pytest.raises(ValidationError):
        EcosystemBlueprint.model_validate(blueprint)


# 6. 信息流引用不存在的 role 被拒绝。
def test_information_flow_referencing_unknown_role_is_rejected() -> None:
    blueprint = _blueprint()
    blueprint["cross_device_information_flows"][0]["to_role_id"] = "r_missing"
    with pytest.raises(ValidationError):
        EcosystemBlueprint.model_validate(blueprint)


# 7. 重复 Evidence ID 被拒绝。
def test_duplicate_evidence_ids_are_rejected() -> None:
    candidate = _model_candidate()
    candidate["evidence_ids"] = ["ev_dup", "ev_dup"]
    with pytest.raises(ValidationError):
        EcosystemOpportunityModelCandidate.model_validate(candidate)


# 8. 模型输出不能包含 gate_status。
def test_model_candidate_cannot_carry_gate_status() -> None:
    candidate = _model_candidate()
    candidate["gate_status"] = "passed"
    with pytest.raises(ValidationError):
        EcosystemOpportunityModelCandidate.model_validate(candidate)


# 9. generated_candidate_count 超过 5 被拒绝。
def test_generated_candidate_count_above_five_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EcosystemOpportunityCoverage.model_validate(_coverage(generated_candidate_count=6))


# 10. advancing_candidate_count 大于生成数被拒绝。
def test_advancing_candidate_count_above_generated_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EcosystemOpportunityCoverage.model_validate(
            _coverage(generated_candidate_count=2, advancing_candidate_count=3)
        )
    # ecosystem_service_count 也不能超过生成数。
    with pytest.raises(ValidationError):
        EcosystemOpportunityCoverage.model_validate(
            _coverage(generated_candidate_count=1, ecosystem_service_count=2)
        )


# 11. Gap ID 确定且稳定，与顺序无关。
def test_gap_id_is_deterministic_and_stable() -> None:
    first = ecosystem_opportunity_gap_id("需要哪些证据？", ["eco_b", "eco_a"])
    second = ecosystem_opportunity_gap_id("需要哪些证据？", ["eco_a", "eco_b"])
    other = ecosystem_opportunity_gap_id("另一个问题？", ["eco_a", "eco_b"])
    assert first == second
    assert first.startswith("gap_")
    assert first != other


def _gated_candidate() -> EcosystemOpportunityCandidate:
    data = _model_candidate()
    data["gate_status"] = "passed"
    data["gate_issues"] = []
    return EcosystemOpportunityCandidate.model_validate(data)


def _artifact(status: str = "completed") -> EcosystemOpportunityArtifact:
    payload = EcosystemOpportunityPayload.model_validate(
        {
            "schema_name": "ecosystem_opportunity_portfolio",
            "schema_version": "1.0",
            "summary": "one advancing ecosystem opportunity",
            "summary_evidence_ids": ["ev_user_1"],
            "opportunities": [_gated_candidate().model_dump(mode="json")],
            "portfolio_gaps": [],
            "coverage": _coverage(),
        }
    )
    return EcosystemOpportunityArtifact(
        artifact_id="artifact_eco_1",
        task_id="task_eco_1",
        artifact_type=ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value,
        schema_version="1.0",
        status=ResearchTaskStatus(status),
        payload=payload,
        evidence_ids=["ev_user_1", "ev_comp_1"],
        contradictions=[],
        unknowns=[],
        quality_score=88.0,
        errors=[],
    )


# 12. ResearchArtifact 双向转换成功（并回填缺失 gap_id）。
def test_research_artifact_round_trips() -> None:
    artifact = _artifact()
    research = artifact.to_research_artifact()
    assert isinstance(research, ResearchArtifact)
    assert research.artifact_type == "ecosystem_opportunity"
    restored = EcosystemOpportunityArtifact.from_research_artifact(research)
    assert restored.model_dump() == artifact.model_dump()


def test_from_research_artifact_backfills_missing_gap_id() -> None:
    payload = {
        "schema_name": "ecosystem_opportunity_portfolio",
        "schema_version": "1.0",
        "summary": "evidence insufficient, only gaps",
        "summary_evidence_ids": [],
        "opportunities": [],
        "portfolio_gaps": [
            {
                "question": "需要哪类企业设备能力证据？",
                "reason": "设备能力未确认",
                "required_evidence_types": ["device_capability_evidence"],
                "affected_opportunity_ids": [],
            }
        ],
        "coverage": _coverage(
            generated_candidate_count=0,
            advancing_candidate_count=0,
            ecosystem_service_count=0,
            cited_user_evidence_count=0,
            cited_competitor_evidence_count=0,
            handoff_status="blocked",
        ),
    }
    research = ResearchArtifact(
        artifact_id="artifact_eco_gap",
        task_id="task_eco_gap",
        artifact_type="ecosystem_opportunity",
        schema_version="1.0",
        status=ResearchTaskStatus.BLOCKED,
        payload=payload,
        evidence_ids=[],
        contradictions=[],
        unknowns=[],
        quality_score=0.0,
        errors=[],
    )
    restored = EcosystemOpportunityArtifact.from_research_artifact(research)
    assert restored.payload.portfolio_gaps[0].gap_id.startswith("gap_")


# 13. Product Technical v1 契约在新增枚举后仍能解析。
def test_product_technical_v1_artifact_still_parses() -> None:
    artifact = ProductTechnicalArtifact(
        artifact_id="artifact_pt",
        task_id="task_pt",
        artifact_type="product_technical",
        schema_version="1.0",
        status=ResearchTaskStatus.BLOCKED,
        payload=ProductTechnicalPayload(
            summary="v1 unchanged",
            summary_evidence_ids=[],
            candidates=[],
            portfolio_gaps=[],
            coverage=ProductTechnicalCoverage(
                generated_candidate_count=0,
                advancing_candidate_count=0,
                cited_user_evidence_count=0,
                cited_competitor_evidence_count=0,
                evidence_context_hash=_HASH,
                handoff_status=ResearchHandoffStatus.BLOCKED,
            ),
        ),
        evidence_ids=[],
        contradictions=[],
        unknowns=[],
        quality_score=0.0,
        errors=[],
    )
    assert artifact.artifact_type == "product_technical"
    assert ResearchAgentType.PRODUCT_TECHNICAL.value == "product_technical"
    assert ResearchAgentType.ECOSYSTEM_OPPORTUNITY.value == "ecosystem_opportunity"
    assert RecoverableAgentType.ECOSYSTEM_OPPORTUNITY.value == "ecosystem_opportunity"


# 14. extra 字段被拒绝。
def test_unknown_fields_are_rejected() -> None:
    blueprint = _blueprint()
    blueprint["unexpected"] = "nope"
    with pytest.raises(ValidationError):
        EcosystemBlueprint.model_validate(blueprint)


# 15. Evidence 不足时允许零个或少于三个候选，但必须能表达 portfolio_gaps。
def test_insufficient_evidence_allows_few_candidates_with_gaps() -> None:
    empty = EcosystemOpportunityPayload.model_validate(
        {
            "schema_name": "ecosystem_opportunity_portfolio",
            "schema_version": "1.0",
            "summary": "no advancing candidate",
            "summary_evidence_ids": [],
            "opportunities": [],
            "portfolio_gaps": [
                {
                    "gap_id": ecosystem_opportunity_gap_id("缺什么？", []),
                    "question": "缺什么？",
                    "reason": "证据不足",
                    "required_evidence_types": ["user_event_evidence"],
                    "affected_opportunity_ids": [],
                }
            ],
            "coverage": _coverage(
                generated_candidate_count=0,
                advancing_candidate_count=0,
                ecosystem_service_count=0,
                cited_user_evidence_count=0,
                cited_competitor_evidence_count=0,
                handoff_status="blocked",
            ),
        }
    )
    assert empty.opportunities == []
    assert len(empty.portfolio_gaps) == 1

    two = copy.deepcopy(_model_candidate())
    two_payload = EcosystemOpportunityPayload.model_validate(
        {
            "schema_name": "ecosystem_opportunity_portfolio",
            "schema_version": "1.0",
            "summary": "two candidates, fewer than three is valid",
            "summary_evidence_ids": [],
            "opportunities": [
                {**_gated_candidate().model_dump(mode="json"), "opportunity_id": "eco_a"},
                {**_gated_candidate().model_dump(mode="json"), "opportunity_id": "eco_b"},
            ],
            "portfolio_gaps": [],
            "coverage": _coverage(
                generated_candidate_count=2,
                advancing_candidate_count=2,
                ecosystem_service_count=2,
            ),
        }
    )
    assert len(two_payload.opportunities) == 2
    assert two["scope_level"] == "ecosystem_service"
