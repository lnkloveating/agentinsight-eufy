from copy import deepcopy

from app.workflows.contracts import (
    ResearchAgentType,
    ResearchArtifact,
    ResearchHandoffStatus,
    ResearchTaskStatus,
)
from app.workflows.handoff import affected_research_agents, build_research_handoff


def _user_artifact(*, status: ResearchTaskStatus = ResearchTaskStatus.COMPLETED):
    return ResearchArtifact(
        artifact_id="artifact_user",
        task_id="task_user",
        artifact_type=ResearchAgentType.USER_RESEARCH,
        status=status,
        payload={
            "summary": "Users still combine package context manually.",
            "summary_evidence_ids": ["ev_user"],
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
        evidence_ids=["ev_user"],
        quality_score=85,
    )


def _competitor_artifact(
    *,
    status: ResearchTaskStatus = ResearchTaskStatus.COMPLETED,
    with_gaps: bool = False,
):
    coverage = {
        "scope_label": "Target Doorbell",
        "official_product_evidence_ids": ["ev_competitor"],
        "price_channel_evidence_ids": ["ev_competitor"],
        "user_review_evidence_ids": [] if with_gaps else ["ev_competitor"],
        "complete": not with_gaps,
    }
    research_gaps = (
        [
            {
                "scope_label": "Target Doorbell",
                "dimension": "user_review",
                "question": "Which recurring owner opinions remain missing?",
                "reason": "Only official and channel evidence is covered.",
                "severity": "medium",
            }
        ]
        if with_gaps
        else []
    )
    return ResearchArtifact(
        artifact_id="artifact_competitor",
        task_id="task_competitor",
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        status=status,
        payload={
            "schema_name": "competitor_synthesis_intelligence",
            "schema_version": "1.0",
            "supervisor_mode": "a2a_specialists_then_evidence_bounded_synthesis",
            "specialist_outputs": [
                {"specialist_type": "official_product"},
                {"specialist_type": "price_channel"},
                {"specialist_type": "user_review"},
            ],
            "summary": "The current product detects packages.",
            "summary_evidence_ids": ["ev_competitor"],
            "product_profiles": [
                {
                    "scope_label": "Target Doorbell",
                    "strengths": [
                        {
                            "point_id": "point_detection",
                            "dimension": "official_product",
                            "statement": "Package detection is documented.",
                            "explanation": "Official evidence supports the capability.",
                            "confidence": 0.9,
                            "evidence_ids": ["ev_competitor"],
                        }
                    ],
                    "weaknesses": [],
                    "tradeoffs": [],
                }
            ],
            "comparative_insights": [],
            "opportunity_signals": [
                {
                    "signal_id": "signal_package_context",
                    "scope_labels": ["Target Doorbell"],
                    "statement": "Package context warrants product validation.",
                    "rationale": "Detection alone does not explain risk.",
                    "validation_questions": ["Which context signals change risk?"],
                    "hypothesis_status": "requires_product_agent_validation",
                    "evidence_ids": ["ev_competitor"],
                }
            ],
            "research_gaps": research_gaps,
            "coverage_matrix": [coverage],
            "evidence_audit": {
                "status": "passed_with_gaps" if with_gaps else "passed",
                "allowed_evidence_count": 1,
                "cited_evidence_count": 1,
                "specialist_output_count": 3,
                "requested_product_count": 1,
                "represented_product_count": 1,
                "complete_product_count": 0 if with_gaps else 1,
                "independent_source_count": 1,
                "evidence_context_hash": "b" * 64,
            },
            "synthesis_status": "partial" if with_gaps else "completed",
        },
        evidence_ids=["ev_competitor"],
        quality_score=80 if with_gaps else 90,
    )


def _artifacts(user=None, competitor=None):
    return {
        ResearchAgentType.USER_RESEARCH.value: user or _user_artifact(),
        ResearchAgentType.COMPETITOR_RESEARCH.value: (
            competitor or _competitor_artifact()
        ),
    }


def test_completed_research_builds_ready_handoff() -> None:
    handoff = build_research_handoff(_artifacts())

    assert handoff.status is ResearchHandoffStatus.READY
    assert handoff.ready_for_product_technical is True
    assert handoff.merged_evidence_ids == ["ev_competitor", "ev_user"]
    assert handoff.competitor_projection is not None
    assert handoff.competitor_projection.opportunity_signal_ids == [
        "signal_package_context"
    ]
    assert handoff.competitor_projection.gaps == []


def test_partial_competitor_with_audited_gaps_can_advance() -> None:
    handoff = build_research_handoff(
        _artifacts(
            competitor=_competitor_artifact(
                status=ResearchTaskStatus.PARTIAL, with_gaps=True
            )
        )
    )

    assert handoff.status is ResearchHandoffStatus.READY_WITH_GAPS
    assert handoff.ready_for_product_technical is True
    assert handoff.competitor_projection is not None
    assert handoff.competitor_projection.gaps[0].missing_dimensions == ["user_review"]
    assert handoff.competitor_projection.gaps[0].research_questions == [
        "Which recurring owner opinions remain missing?"
    ]


def test_foundation_or_unbounded_competitor_artifact_is_blocked() -> None:
    artifact = _competitor_artifact()
    artifact.payload = {
        "schema_name": "competitor_a2a_foundation",
        "specialist_outputs": [],
    }
    handoff = build_research_handoff(_artifacts(competitor=artifact))

    assert handoff.status is ResearchHandoffStatus.BLOCKED
    assert handoff.ready_for_product_technical is False
    assert handoff.issues == ["invalid_competitor_synthesis_artifact"]
    assert affected_research_agents(handoff) == {
        ResearchAgentType.COMPETITOR_RESEARCH
    }


def test_payload_cannot_cite_evidence_outside_parent_artifact() -> None:
    artifact = _competitor_artifact()
    payload = deepcopy(artifact.payload)
    payload["summary_evidence_ids"] = ["ev_not_in_parent"]
    artifact.payload = payload

    handoff = build_research_handoff(_artifacts(competitor=artifact))

    assert handoff.status is ResearchHandoffStatus.BLOCKED
    assert "competitor_payload_evidence_outside_artifact" in handoff.issues
