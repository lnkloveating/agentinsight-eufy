from copy import deepcopy

import pytest

from app.agents.product_technical import (
    ProductTechnicalModelOutput,
    ProductTechnicalOutputValidator,
    ProductTechnicalValidationError,
)
from app.schemas.project import ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchBudget,
    ResearchTask,
    ResearchTaskStatus,
)
from app.workflows.handoff import build_research_handoff


def _user_artifact() -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="artifact_user_dynamic",
        task_id="task_user_dynamic",
        artifact_type=ResearchAgentType.USER_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={
            "summary": "用户需要自己组合多个通知理解当前事件。",
            "summary_evidence_ids": ["ev_user_dynamic"],
            "event_chains": [],
            "pain_points": [],
            "unmet_needs": [],
            "sample_biases": [],
            "research_gaps": [],
            "evidence_coverage": {
                "available_evidence_count": 1,
                "included_evidence_count": 1,
                "cited_evidence_count": 1,
                "independent_domain_count": 1,
                "user_opinion_evidence_count": 1,
                "context_hash": "a" * 64,
            },
        },
        evidence_ids=["ev_user_dynamic"],
        quality_score=90,
    )


def _competitor_artifact() -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="artifact_competitor_dynamic",
        task_id="task_competitor_dynamic",
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={
            "schema_name": "competitor_synthesis_intelligence",
            "schema_version": "1.0",
            "supervisor_mode": "a2a_specialists_then_evidence_bounded_synthesis",
            "specialist_outputs": [{}, {}, {}],
            "summary": "竞品能力仍存在上下文解释缺口。",
            "summary_evidence_ids": ["ev_competitor_dynamic"],
            "product_profiles": [
                {
                    "scope_label": "动态测试产品",
                    "strengths": [
                        {
                            "point_id": "point_dynamic",
                            "dimension": "official_product",
                            "statement": "已有基础事件检测。",
                            "explanation": "官方资料支持。",
                            "confidence": 0.9,
                            "evidence_ids": ["ev_competitor_dynamic"],
                        }
                    ],
                    "weaknesses": [],
                    "tradeoffs": [],
                }
            ],
            "comparative_insights": [],
            "opportunity_signals": [
                {
                    "signal_id": "signal_dynamic_context",
                    "scope_labels": ["动态测试产品"],
                    "statement": "事件解释能力需要产品 Agent 验证。",
                    "rationale": "现有能力只报告单一事件。",
                    "validation_questions": ["哪些上下文能改变建议？"],
                    "hypothesis_status": "requires_product_agent_validation",
                    "evidence_ids": ["ev_competitor_dynamic"],
                }
            ],
            "research_gaps": [],
            "coverage_matrix": [
                {
                    "scope_label": "动态测试产品",
                    "official_product_evidence_ids": ["ev_competitor_dynamic"],
                    "price_channel_evidence_ids": ["ev_competitor_dynamic"],
                    "user_review_evidence_ids": ["ev_competitor_dynamic"],
                    "complete": True,
                }
            ],
            "evidence_audit": {
                "status": "passed",
                "allowed_evidence_count": 1,
                "cited_evidence_count": 1,
                "specialist_output_count": 3,
                "requested_product_count": 1,
                "represented_product_count": 1,
                "complete_product_count": 1,
                "independent_source_count": 1,
                "evidence_context_hash": "b" * 64,
            },
            "synthesis_status": "completed",
        },
        evidence_ids=["ev_competitor_dynamic"],
        quality_score=90,
    )


def _context() -> AgentContext:
    upstream = {
        ResearchAgentType.USER_RESEARCH.value: _user_artifact(),
        ResearchAgentType.COMPETITOR_RESEARCH.value: _competitor_artifact(),
    }
    return AgentContext(
        project_id="proj_dynamic",
        brief=ResearchBrief(
            question="分析当前品类未来产品机会",
            category="动态品类",
            target_user="目标用户",
            region="US",
            scenarios=[],
        ),
        iteration=0,
        upstream_artifacts=upstream,
        research_handoff=build_research_handoff(upstream),
    )


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_product_technical",
        project_id="proj_dynamic",
        agent_type=ResearchAgentType.PRODUCT_TECHNICAL,
        goal="动态生成未来产品机会",
        budget=ResearchBudget(deadline_seconds=180),
    )


def _candidate(index: int, *, availability: str = "available") -> dict[str, object]:
    return {
        "candidate_id": f"future_opportunity_{index}",
        "name": f"由当前证据生成的机会 {index}",
        "target_user": {"persona_ids": [f"persona_{index}"], "description": "目标用户"},
        "problem": {"pain_ids": [f"pain_{index}"], "description": "需要理解事件上下文"},
        "event_understanding": {
            "base_event": {"type": f"base_event_{index}", "source": "设备事件接口"},
            "event_state": {"type": f"state_{index}", "source": "设备状态接口"},
            "context_signals": [
                {
                    "type": f"context_a_{index}",
                    "source": "授权上下文接口 A",
                    "availability": availability,
                    "authorization": "用户明确授权",
                    "freshness": "一分钟内",
                    "latency_ms": 200,
                    "confidence": 0.9,
                    "fallback": "缺失时不做高确定性推断",
                },
                {
                    "type": f"context_b_{index}",
                    "source": "授权上下文接口 B",
                    "availability": "available",
                    "authorization": "用户明确授权",
                    "freshness": "五分钟内",
                    "latency_ms": 300,
                    "confidence": 0.85,
                    "fallback": "退化为普通通知",
                },
            ],
            "inference": f"结合事件状态和上下文判断机会 {index}",
            "risk_or_value": f"降低用户手动判断成本 {index}",
            "recommended_action": f"给出可解释行动建议 {index}",
        },
        "competitor_gap_ids": ["signal_dynamic_context"],
        "technical_assessment": {
            "data_requirements": ["设备事件和授权上下文"],
            "required_capabilities": ["事件关联和规则降级"],
            "privacy_constraints": ["仅处理授权数据"],
            "feasibility_summary": "现有接口可支持最小验证。",
            "demo_validation_plan": "用授权样本验证事件到建议的链路。",
        },
        "evidence_ids": ["ev_user_dynamic", "ev_competitor_dynamic"],
    }


def _output(candidates: list[dict[str, object]]) -> ProductTechnicalModelOutput:
    return ProductTechnicalModelOutput.model_validate(
        {
            "summary": "根据当前项目证据动态生成机会。",
            "summary_evidence_ids": ["ev_user_dynamic", "ev_competitor_dynamic"],
            "candidates": candidates,
            "portfolio_gaps": [],
            "unknowns": [],
        }
    )


def test_three_distinct_evidence_bounded_candidates_complete() -> None:
    artifact = ProductTechnicalOutputValidator().validate(
        _task(), _context(), _output([_candidate(1), _candidate(2), _candidate(3)])
    )
    payload = artifact.payload

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert payload["coverage"]["generated_candidate_count"] == 3
    assert payload["coverage"]["advancing_candidate_count"] == 3
    assert {item["name"] for item in payload["candidates"]} == {
        "由当前证据生成的机会 1",
        "由当前证据生成的机会 2",
        "由当前证据生成的机会 3",
    }


def test_fewer_than_three_is_partial_and_reports_gap_without_padding() -> None:
    artifact = ProductTechnicalOutputValidator().validate(
        _task(), _context(), _output([_candidate(1), _candidate(2)])
    )

    assert artifact.status is ResearchTaskStatus.PARTIAL
    assert len(artifact.payload["candidates"]) == 2
    assert artifact.payload["coverage"]["advancing_candidate_count"] == 2
    assert "补足到 3 个" in artifact.payload["portfolio_gaps"][-1]["question"]


def test_unavailable_context_signal_blocks_candidate_from_advancing() -> None:
    artifact = ProductTechnicalOutputValidator().validate(
        _task(), _context(), _output([_candidate(1, availability="unavailable")])
    )

    assert artifact.status is ResearchTaskStatus.BLOCKED
    candidate = artifact.payload["candidates"][0]
    assert candidate["gate_status"] == "blocked"
    assert any("context_signal_not_available" in issue for issue in candidate["gate_issues"])


def test_hallucinated_evidence_id_is_rejected() -> None:
    candidate = deepcopy(_candidate(1))
    candidate["evidence_ids"] = ["ev_user_dynamic", "ev_hallucinated"]

    with pytest.raises(ProductTechnicalValidationError) as exc_info:
        ProductTechnicalOutputValidator().validate(
            _task(), _context(), _output([candidate])
        )

    assert exc_info.value.details["unsupported_evidence_ids"] == ["ev_hallucinated"]


def test_duplicate_candidate_event_signature_is_rejected() -> None:
    duplicate = deepcopy(_candidate(1))
    duplicate["candidate_id"] = "different_id"
    duplicate["name"] = "different name"

    with pytest.raises(ProductTechnicalValidationError):
        ProductTechnicalOutputValidator().validate(
            _task(), _context(), _output([_candidate(1), duplicate])
        )
