from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agents.competitor.ecosystem_contracts import (
    CompetitorEcosystemModelOutput,
    EcosystemCapabilityAssessment,
)
from app.agents.competitor.ecosystem_validation import (
    CompetitorEcosystemOutputValidator,
    CompetitorEcosystemValidationError,
)
from app.integrations.a2a import (
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
)
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTaskStatus,
)

PRODUCT = "Target Doorbell"
TARGET_ECOSYSTEM = "eufy Security"
COMPARISON_ECOSYSTEM = "Ring"


def _evidence(evidence_id: str, claim_type: str, domain: str) -> AgentEvidence:
    return AgentEvidence(
        evidence_id=evidence_id,
        title=evidence_id,
        original_excerpt=f"Controlled excerpt for {evidence_id}.",
        claim_type=claim_type,
        status="verified",
        source_type="webpage",
        source_url=f"https://{domain}/{evidence_id}",
        source_domain=domain,
        product=PRODUCT,
        region="US",
        confidence=0.9,
        authority_score=0.9,
        recency_score=0.8,
        diversity_score=0.8,
    )


def _context() -> AgentEvidenceContext:
    items = [
        _evidence("ev_official", "vendor_claim", "vendor.example"),
        _evidence("ev_price", "price_observation", "store.example"),
        _evidence("ev_review", "user_opinion", "review.example"),
    ]
    return AgentEvidenceContext(
        items=items,
        available_evidence_count=3,
        included_evidence_count=3,
        omitted_evidence_count=0,
        context_hash="a" * 64,
    )


def _specialists() -> list[CompetitorSpecialistArtifact]:
    return [
        CompetitorSpecialistArtifact(
            a2a_task_id=f"a2a_{specialist.value}",
            request_id=f"request_{specialist.value}",
            specialist_type=specialist,
            status=ResearchTaskStatus.COMPLETED,
            findings=[
                CompetitorFinding(
                    finding_id=f"finding_{specialist.value}",
                    category=specialist.value,
                    statement=f"Controlled {specialist.value} finding.",
                    evidence_ids=[evidence_id],
                    confidence=0.9,
                )
            ],
            evidence_ids=[evidence_id],
            quality_score=90,
        )
        for specialist, evidence_id in (
            (CompetitorSpecialistType.OFFICIAL_PRODUCT, "ev_official"),
            (CompetitorSpecialistType.PRICE_CHANNEL, "ev_price"),
            (CompetitorSpecialistType.USER_REVIEW, "ev_review"),
        )
    ]


def _product_fact_artifact() -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id="artifact_product_facts",
        task_id="task_ecosystem",
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        status=ResearchTaskStatus.COMPLETED,
        payload={"schema_name": "competitor_synthesis_intelligence"},
        evidence_ids=["ev_official", "ev_price", "ev_review"],
        quality_score=90,
    )


def _output() -> dict[str, object]:
    return {
        "summary": "The bounded evidence covers one ecosystem capability.",
        "summary_evidence_ids": ["ev_official"],
        "ecosystem_profiles": [
            {
                "ecosystem_label": TARGET_ECOSYSTEM,
                "role": "target",
                "product_scope_labels": [PRODUCT],
                "assessments": [
                    {
                        "assessment_id": "assessment_safety",
                        "dimension": "safety_goal_coverage",
                        "status": "supported",
                        "statement": "Package detection covers a bounded safety goal.",
                        "explanation": "Official evidence documents the capability.",
                        "source_dimensions": ["official_product"],
                        "evidence_ids": ["ev_official"],
                        "confidence": 0.9,
                        "unknown_reason": None,
                    },
                    {
                        "assessment_id": "assessment_temporal_unknown",
                        "dimension": "temporal_state_understanding",
                        "status": "unknown",
                        "statement": "Cross-time state maintenance is not established.",
                        "explanation": "No eligible fact covers state duration.",
                        "source_dimensions": [],
                        "evidence_ids": [],
                        "confidence": 0,
                        "unknown_reason": "No eligible specialist Evidence covers this dimension.",
                    },
                ],
            }
        ],
        "comparison_insights": [],
        "opportunity_signals": [
            {
                "signal_id": "signal_state",
                "ecosystem_labels": [TARGET_ECOSYSTEM],
                "gap_dimensions": ["temporal_state_understanding"],
                "statement": "Continuous state understanding merits validation.",
                "rationale": "Detection exists while temporal state remains unknown.",
                "validation_questions": ["Can the ecosystem maintain event state over time?"],
                "evidence_ids": ["ev_official"],
                "hypothesis_status": "requires_ecosystem_opportunity_validation",
            }
        ],
        "research_gaps": [
            {
                "ecosystem_label": TARGET_ECOSYSTEM,
                "dimension": "temporal_state_understanding",
                "question": "Which evidence establishes cross-time state maintenance?",
                "reason": "The current facts only establish package detection.",
                "severity": "high",
            }
        ],
        "unknowns": [],
    }


def _validate(output: dict[str, object]) -> ResearchArtifact:
    return CompetitorEcosystemOutputValidator().validate(
        artifact_id="artifact_ecosystem",
        task_id="task_ecosystem",
        target_ecosystems=[TARGET_ECOSYSTEM],
        comparison_ecosystems=[COMPARISON_ECOSYSTEM],
        product_scope=[PRODUCT],
        specialist_artifacts=_specialists(),
        product_fact_synthesis=_product_fact_artifact(),
        evidence_context=_context(),
        output=CompetitorEcosystemModelOutput.model_validate(output),
    )


def test_unknown_assessment_cannot_disguise_a_factual_claim() -> None:
    with pytest.raises(ValidationError):
        EcosystemCapabilityAssessment.model_validate(
            {
                "assessment_id": "unknown_with_citation",
                "dimension": "offline_fallback",
                "status": "unknown",
                "statement": "Offline fallback is unknown.",
                "explanation": "The source is insufficient.",
                "source_dimensions": ["official_product"],
                "evidence_ids": ["ev_official"],
                "confidence": 0,
                "unknown_reason": "Coverage is insufficient.",
            }
        )


def test_non_unknown_assessment_requires_evidence_and_source_lineage() -> None:
    with pytest.raises(ValidationError):
        EcosystemCapabilityAssessment.model_validate(
            {
                "assessment_id": "unsupported_claim",
                "dimension": "offline_fallback",
                "status": "limited",
                "statement": "Offline fallback is limited.",
                "explanation": "No citation was supplied.",
                "source_dimensions": [],
                "evidence_ids": [],
                "confidence": 0.5,
            }
        )


def test_validator_builds_partial_twelve_dimension_ecosystem_coverage() -> None:
    artifact = _validate(_output())

    assert artifact.status is ResearchTaskStatus.PARTIAL
    assert artifact.schema_version == "2.0"
    assert artifact.payload["schema_name"] == "competitor_ecosystem_analysis"
    assert artifact.payload["synthesis_status"] == "partial"
    target, comparison = artifact.payload["coverage_matrix"]
    assert target["evidence_backed_dimension_count"] == 1
    assert target["unknown_dimension_count"] == 11
    assert comparison["unknown_dimension_count"] == 12
    assert artifact.payload["evidence_audit"]["status"] == "passed_with_gaps"
    assert len(artifact.payload["research_gaps"]) == 23


def test_validator_rejects_evidence_outside_specialist_outputs() -> None:
    output = _output()
    output["summary_evidence_ids"] = ["ev_not_allowed"]

    with pytest.raises(CompetitorEcosystemValidationError) as exc_info:
        _validate(output)

    assert exc_info.value.details == {"unsupported_evidence_ids": ["ev_not_allowed"]}


def test_one_product_cannot_be_mapped_to_two_ecosystems() -> None:
    output = deepcopy(_output())
    output["ecosystem_profiles"].append(  # type: ignore[union-attr]
        {
            "ecosystem_label": COMPARISON_ECOSYSTEM,
            "role": "comparison",
            "product_scope_labels": [PRODUCT],
            "assessments": [
                {
                    "assessment_id": "ring_safety",
                    "dimension": "safety_goal_coverage",
                    "status": "supported",
                    "statement": "A bounded capability is documented.",
                    "explanation": "The test deliberately duplicates product ownership.",
                    "source_dimensions": ["official_product"],
                    "evidence_ids": ["ev_official"],
                    "confidence": 0.9,
                    "unknown_reason": None,
                }
            ],
        }
    )

    with pytest.raises(CompetitorEcosystemValidationError) as exc_info:
        _validate(output)

    assert exc_info.value.details["product"] == PRODUCT


def test_validator_requires_one_output_from_each_fact_specialist() -> None:
    with pytest.raises(CompetitorEcosystemValidationError) as exc_info:
        CompetitorEcosystemOutputValidator().validate(
            artifact_id="artifact_ecosystem",
            task_id="task_ecosystem",
            target_ecosystems=[TARGET_ECOSYSTEM],
            comparison_ecosystems=[COMPARISON_ECOSYSTEM],
            product_scope=[PRODUCT],
            specialist_artifacts=_specialists()[:-1],
            product_fact_synthesis=_product_fact_artifact(),
            evidence_context=_context(),
            output=CompetitorEcosystemModelOutput.model_validate(_output()),
        )

    assert exc_info.value.details["specialist_types"] == [
        "official_product",
        "price_channel",
    ]
