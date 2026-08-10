from app.application.source_recovery.gaps import AgentGapProjector
from app.schemas.source_recovery import AgentGapSeverity, RecoverableAgentType
from app.workflows.contracts import ResearchArtifact, ResearchTaskStatus


def _artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    payload: dict[str, object],
) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id=artifact_id,
        task_id=f"task_{artifact_type}",
        artifact_type=artifact_type,
        status=ResearchTaskStatus.PARTIAL,
        payload=payload,
        quality_score=70,
    )


def test_user_research_gap_gets_stable_id_across_artifact_versions() -> None:
    payload = {
        "research_gaps": [
            {
                "question": "How often do packages remain exposed after delivery?",
                "reason": "Current reviews do not contain a representative frequency sample.",
                "severity": "high",
                "recommended_source_types": ["authorized_interview", "survey"],
            }
        ]
    }
    first = AgentGapProjector().project(
        _artifact(
            artifact_id="artifact_user_v1",
            artifact_type="user_research",
            payload=payload,
        ),
        RecoverableAgentType.USER_RESEARCH,
    )
    second = AgentGapProjector().project(
        _artifact(
            artifact_id="artifact_user_v2",
            artifact_type="user_research",
            payload=payload,
        ),
        RecoverableAgentType.USER_RESEARCH,
    )

    assert len(first) == 1
    assert first[0].gap_id == second[0].gap_id
    assert first[0].severity is AgentGapSeverity.HIGH
    assert first[0].recommended_source_types == ["authorized_interview", "survey"]
    assert first[0].source_path == "payload.research_gaps[0]"


def test_competitor_specialist_and_synthesis_gaps_share_one_contract() -> None:
    artifact = _artifact(
        artifact_id="artifact_competitor",
        artifact_type="competitor_research",
        payload={
            "schema_name": "competitor_synthesis_intelligence",
            "research_gaps": [
                {
                    "scope_label": "Ring Doorbell",
                    "dimension": "cross_dimension",
                    "question": "Does the capability work without a subscription?",
                    "reason": "Official and channel sources disagree.",
                    "severity": "medium",
                }
            ],
            "specialist_outputs": [
                {
                    "payload": {
                        "schema_name": "price_channel_intelligence",
                        "research_gaps": [
                            {
                                "scope_label": "Ring Doorbell",
                                "question": "What is the current US subscription price?",
                                "reason": "No recent dated price observation is available.",
                                "severity": "high",
                                "recommended_source_types": ["official_pricing_page"],
                            }
                        ],
                    }
                }
            ],
        },
    )

    gaps = AgentGapProjector().project(artifact, RecoverableAgentType.COMPETITOR_RESEARCH)

    assert len(gaps) == 2
    assert {gap.scope_label for gap in gaps} == {"Ring Doorbell"}
    assert {gap.severity for gap in gaps} == {
        AgentGapSeverity.MEDIUM,
        AgentGapSeverity.HIGH,
    }
    assert any("specialist_outputs" in gap.source_path for gap in gaps)


def test_product_gap_keeps_backend_owned_id_and_future_agent_shape_is_supported() -> None:
    product = AgentGapProjector().project(
        _artifact(
            artifact_id="artifact_product",
            artifact_type="product_technical",
            payload={
                "portfolio_gaps": [
                    {
                        "gap_id": "gap_backend_owned",
                        "question": "Is the authorized Home Mode signal available?",
                        "reason": "The candidate depends on this context signal.",
                        "required_evidence_types": ["technical_api_fact"],
                        "affected_candidate_ids": ["candidate_package_risk"],
                    }
                ]
            },
        ),
        RecoverableAgentType.PRODUCT_TECHNICAL,
    )
    commercial = AgentGapProjector().project(
        _artifact(
            artifact_id="artifact_commercial",
            artifact_type="commercial_evaluation",
            payload={
                "commercial_gaps": [
                    {
                        "question": "What is the expected support cost per active household?",
                        "reason": "No enterprise cost baseline was supplied.",
                        "required_evidence_types": ["commercial_cost_data"],
                    }
                ]
            },
        ),
        RecoverableAgentType.COMMERCIAL_EVALUATION,
    )

    assert product[0].gap_id == "gap_backend_owned"
    assert product[0].affected_candidate_ids == ["candidate_package_risk"]
    assert commercial[0].agent_type is RecoverableAgentType.COMMERCIAL_EVALUATION
    assert commercial[0].severity is AgentGapSeverity.UNKNOWN
