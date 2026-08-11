from copy import deepcopy

import pytest

from app.agents.ecosystem_opportunity import (
    DeviceCapabilityFact,
    DeviceCapabilityGraphContext,
    EcosystemOpportunityModelOutput,
    EcosystemOpportunityOutputValidator,
    EcosystemOpportunityValidationError,
)
from app.core.config import Settings
from app.main import create_app
from app.workflows.contracts import (
    AgentContext,
    CompetitorResearchProjection,
    ResearchAgentType,
    ResearchArtifact,
    ResearchArtifactProjection,
    ResearchBudget,
    ResearchHandoff,
    ResearchHandoffStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from tests.research_brief import home_safety_brief


def _artifact(agent_type: ResearchAgentType, evidence_id: str) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id=f"artifact_{agent_type.value}",
        task_id=f"task_{agent_type.value}",
        artifact_type=agent_type,
        status=ResearchTaskStatus.COMPLETED,
        payload={},
        evidence_ids=[evidence_id],
        quality_score=90,
    )


def _context() -> AgentContext:
    user = _artifact(ResearchAgentType.USER_RESEARCH, "ev_user")
    competitor = _artifact(ResearchAgentType.COMPETITOR_RESEARCH, "ev_competitor")
    return AgentContext(
        project_id="proj_ecosystem",
        brief=home_safety_brief(),
        iteration=0,
        upstream_artifacts={
            ResearchAgentType.USER_RESEARCH.value: user,
            ResearchAgentType.COMPETITOR_RESEARCH.value: competitor,
        },
        research_handoff=ResearchHandoff(
            status=ResearchHandoffStatus.READY,
            ready_for_ecosystem_opportunity=True,
            user_research=ResearchArtifactProjection(
                artifact_id=user.artifact_id,
                task_id=user.task_id,
                artifact_type=ResearchAgentType.USER_RESEARCH,
                status=user.status,
                evidence_ids=user.evidence_ids,
                quality_score=user.quality_score,
            ),
            competitor_research=ResearchArtifactProjection(
                artifact_id=competitor.artifact_id,
                task_id=competitor.task_id,
                artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
                status=competitor.status,
                evidence_ids=competitor.evidence_ids,
                quality_score=competitor.quality_score,
            ),
            competitor_projection=CompetitorResearchProjection(
                schema_name="competitor_ecosystem_analysis",
                synthesis_status="completed",
                evidence_audit_status="passed",
                ecosystem_scope=["eufy Security", "Ring"],
                opportunity_signal_ids=["signal_cross_device_gap"],
            ),
            merged_evidence_ids=["ev_user", "ev_competitor"],
        ),
    )


def _graph() -> DeviceCapabilityGraphContext:
    fact = DeviceCapabilityFact(
        catalog_device_id="device_homebase",
        manufacturer="eufy",
        product_name="HomeBase",
        model="S380",
        category="local_hub",
        lifecycle_status="active",
        capability_key="local_event_reasoning",
        capability_name="本地事件推理",
        kind="compute",
        assertion="supported",
        availability="available",
        confidence=0.9,
        data_scope="homebase_local",
        authorization_required=True,
        offline_support="degraded",
        fallback="仅发送基础通知",
        evidence_ids=["ev_device"],
    )
    return DeviceCapabilityGraphContext(
        facts=[fact],
        included_device_count=1,
        included_claim_count=1,
        omitted_claim_count=0,
        evidence_ids=["ev_device"],
        issues=[],
        context_hash="c" * 64,
    )


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_ecosystem_opportunity",
        project_id="proj_ecosystem",
        agent_type=ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
        goal="动态生成生态机会",
        budget=ResearchBudget(deadline_seconds=180),
    )


def _candidate(index: int, capability: str = "本地事件推理") -> dict[str, object]:
    return {
        "opportunity_id": f"eco_dynamic_{index}",
        "name": f"动态生态机会 {index}",
        "scope_level": "ecosystem_service",
        "target_user": {
            "persona_ids": [f"persona_{index}"],
            "description": "授权使用家庭安防设备的家庭",
        },
        "problem": {
            "pain_ids": [f"pain_{index}"],
            "description": "用户需要手工拼接多个设备事件",
        },
        "safety_goal": f"持续理解第 {index} 类家庭安全风险",
        "ecosystem_blueprint": {
            "required_device_roles": [
                {
                    "role_id": f"role_sensor_{index}",
                    "role_type": "primary_perception",
                    "description": "采集经过授权的安全事件",
                    "required_capabilities": [],
                    "optional": False,
                    "evidence_ids": [],
                },
                {
                    "role_id": f"role_hub_{index}",
                    "role_type": "local_reasoning_hub",
                    "description": "在本地关联多个事件",
                    "required_capabilities": [capability],
                    "optional": False,
                    "evidence_ids": ["ev_device"] if capability == "本地事件推理" else [],
                },
            ],
            "required_capabilities": [capability],
            "cross_device_information_flows": [
                {
                    "flow_id": f"flow_{index}",
                    "from_role_id": f"role_sensor_{index}",
                    "to_role_id": f"role_hub_{index}",
                    "data_type": "authorized_event_metadata",
                    "purpose": "理解连续安全状态",
                    "privacy_constraints": ["只处理最少事件元数据"],
                    "fallback": "退化为基础通知",
                }
            ],
            "deployment_target": "hybrid",
            "privacy_boundary": "原始媒体默认不离开设备",
            "permission_boundary": "高影响动作需要用户批准",
            "offline_behavior": "离线时执行本地低风险规则",
            "fallback_behavior": "证据不足时询问用户",
            "known_blind_spots": ["设备离线会降低上下文完整度"],
        },
        "ai_native_case": {
            "open_ended_goal": "持续守护家庭，而不是只报告单次检测",
            "why_fixed_rules_are_insufficient": "家庭设备、习惯和风险会随时间变化",
            "model_responsibilities": ["解释连续事件和不确定性"],
            "deterministic_responsibilities": ["执行权限和动作边界"],
            "ai_removal_test": {
                "core_value_survives_without_ai": False,
                "rationale": "移除模型后只能执行固定通知规则",
                "lost_capabilities_without_ai": ["开放目标到策略的转换"],
                "evidence_ids": ["ev_user"],
            },
            "learning_or_revision_loop": ["失败场景后修订策略"],
            "safety_constraints": ["不进行医疗诊断"],
        },
        "competitor_gap_ids": ["signal_cross_device_gap"],
        "technical_hypotheses": (
            [] if capability == "本地事件推理" else [f"{capability} 需要进一步验证"]
        ),
        "commercial_hypotheses": ["用户是否愿意为持续守护能力付费需要验证"],
        "validation_plan": {
            "validation_goal": "验证策略在真实部署前是否安全有效",
            "required_scenario_types": ["normal", "failure", "adversarial"],
            "success_conditions": ["正常事件不触发高风险告警"],
            "failure_conditions": ["高风险事件未被升级"],
            "required_data": ["授权事件或模拟事件"],
            "human_review_points": ["启用策略前"],
        },
        "evidence_ids": ["ev_user", "ev_competitor", "ev_device"],
    }


def _output(candidates: list[dict[str, object]]) -> EcosystemOpportunityModelOutput:
    return EcosystemOpportunityModelOutput.model_validate(
        {
            "summary": "用户需要连续理解，竞品生态仍存在跨设备协作缺口。",
            "summary_evidence_ids": ["ev_user", "ev_competitor"],
            "opportunities": candidates,
            "portfolio_gaps": [],
            "unknowns": [],
        }
    )


def test_three_dynamic_grounded_ecosystem_candidates_complete() -> None:
    artifact = EcosystemOpportunityOutputValidator().validate(
        _task(), _context(), _graph(), _output([_candidate(1), _candidate(2), _candidate(3)])
    )

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert artifact.payload["coverage"]["advancing_candidate_count"] == 3
    assert artifact.payload["coverage"]["ecosystem_service_count"] == 3
    assert {item["gate_status"] for item in artifact.payload["opportunities"]} == {
        "passed"
    }


def test_unknown_capability_remains_hypothesis_and_generates_gap() -> None:
    artifact = EcosystemOpportunityOutputValidator().validate(
        _task(), _context(), _graph(), _output([_candidate(1, "跨房间异常行为基线")])
    )

    assert artifact.status is ResearchTaskStatus.PARTIAL
    assert artifact.payload["opportunities"][0]["gate_status"] == "passed"
    assert any(
        "跨房间异常行为基线" in gap["question"]
        for gap in artifact.payload["portfolio_gaps"]
    )


def test_unverified_capability_without_explicit_hypothesis_is_blocked() -> None:
    candidate = _candidate(1, "跨房间异常行为基线")
    candidate["technical_hypotheses"] = []
    artifact = EcosystemOpportunityOutputValidator().validate(
        _task(), _context(), _graph(), _output([candidate])
    )

    assert artifact.status is ResearchTaskStatus.BLOCKED
    assert "unverified_capability_not_hypothesis:跨房间异常行为基线" in artifact.payload[
        "opportunities"
    ][0]["gate_issues"]


def test_hallucinated_evidence_is_rejected() -> None:
    candidate = deepcopy(_candidate(1))
    candidate["evidence_ids"] = ["ev_user", "ev_competitor", "ev_device", "ev_fake"]
    with pytest.raises(EcosystemOpportunityValidationError) as exc_info:
        EcosystemOpportunityOutputValidator().validate(
            _task(), _context(), _graph(), _output([candidate])
        )

    assert exc_info.value.details["unsupported_evidence_ids"] == ["ev_fake"]


def test_public_ecosystem_opportunity_routes_are_registered() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]

    assert "/api/v1/projects/{project_id}/agents/ecosystem-opportunity" in paths
    assert "/api/v1/projects/{project_id}/agents/ecosystem-opportunity/artifacts" in paths
