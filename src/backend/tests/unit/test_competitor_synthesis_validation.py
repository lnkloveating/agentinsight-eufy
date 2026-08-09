from __future__ import annotations

from copy import deepcopy

import pytest

from app.agents.competitor.synthesis_contracts import CompetitorSynthesisModelOutput
from app.agents.competitor.synthesis_validation import (
    CompetitorSynthesisOutputValidator,
    CompetitorSynthesisValidationError,
)
from app.integrations.a2a import (
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
    EvidenceRequest,
)
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchTaskStatus,
)

PRODUCT = "Target Doorbell"


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


def _requests() -> list[EvidenceRequest]:
    return [
        EvidenceRequest(
            request_id=f"request_{specialist.value}",
            project_id="project_synthesis",
            parent_task_id="task_synthesis",
            specialist_type=specialist,
            research_questions=["Analyze controlled evidence."],
            product_scope=[PRODUCT],
            region="US",
            evidence_types=[specialist.value],
            allowed_claim_types=[claim_type],
            minimum_independent_domains=1,
        )
        for specialist, claim_type in (
            (CompetitorSpecialistType.OFFICIAL_PRODUCT, "vendor_claim"),
            (CompetitorSpecialistType.PRICE_CHANNEL, "price_observation"),
            (CompetitorSpecialistType.USER_REVIEW, "user_opinion"),
        )
    ]


def _artifacts() -> list[CompetitorSpecialistArtifact]:
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
                    statement=f"{PRODUCT} controlled {specialist.value} finding.",
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


def _output_dict() -> dict[str, object]:
    return {
        "summary": "The three controlled dimensions are covered.",
        "summary_evidence_ids": ["ev_official", "ev_price", "ev_review"],
        "product_profiles": [
            {
                "scope_label": PRODUCT,
                "strengths": [
                    {
                        "point_id": "strength_capability",
                        "dimension": "official_product",
                        "statement": "The documented capability is a strength.",
                        "explanation": "The official specialist extracted it.",
                        "confidence": 0.9,
                        "evidence_ids": ["ev_official"],
                    }
                ],
                "weaknesses": [
                    {
                        "point_id": "weakness_review",
                        "dimension": "user_review",
                        "statement": "A recurring user friction is a weakness.",
                        "explanation": "The review specialist extracted it.",
                        "confidence": 0.8,
                        "evidence_ids": ["ev_review"],
                    }
                ],
                "tradeoffs": [
                    {
                        "point_id": "tradeoff_price",
                        "dimension": "price_channel",
                        "statement": "The observed price creates a tradeoff.",
                        "explanation": "The price specialist bounded the observation.",
                        "confidence": 0.8,
                        "evidence_ids": ["ev_price"],
                    }
                ],
            }
        ],
        "comparative_insights": [],
        "opportunity_signals": [
            {
                "signal_id": "signal_context",
                "scope_labels": [PRODUCT],
                "statement": "Context-aware handling may merit validation.",
                "rationale": "Capability and user friction coexist.",
                "validation_questions": ["Can event context reduce the friction?"],
                "evidence_ids": ["ev_official", "ev_review"],
            }
        ],
        "research_gaps": [],
        "unknowns": [],
    }


def _validate(output_dict: dict[str, object]):
    return CompetitorSynthesisOutputValidator().validate(
        artifact_id="artifact_synthesis",
        task_id="task_synthesis",
        product_scope=[PRODUCT],
        requests=_requests(),
        specialist_artifacts=_artifacts(),
        evidence_context=_context(),
        output=CompetitorSynthesisModelOutput.model_validate(output_dict),
    )


def test_validator_builds_completed_coverage_matrix_and_hypothesis_signal() -> None:
    artifact = _validate(_output_dict())

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert artifact.payload["schema_name"] == "competitor_synthesis_intelligence"
    assert artifact.payload["evidence_audit"]["status"] == "passed"
    assert artifact.payload["coverage_matrix"][0]["complete"] is True
    assert artifact.payload["opportunity_signals"][0]["hypothesis_status"] == (
        "requires_product_agent_validation"
    )
    assert artifact.evidence_ids == ["ev_official", "ev_price", "ev_review"]


def test_validator_rejects_evidence_not_emitted_by_any_specialist() -> None:
    payload = _output_dict()
    payload["summary_evidence_ids"] = ["ev_official", "ev_unknown"]

    with pytest.raises(CompetitorSynthesisValidationError) as exc_info:
        _validate(payload)

    assert exc_info.value.details == {"unsupported_evidence_ids": ["ev_unknown"]}


def test_validator_rejects_crossing_a_specialist_dimension_boundary() -> None:
    payload = deepcopy(_output_dict())
    profile = payload["product_profiles"][0]  # type: ignore[index]
    profile["strengths"][0]["evidence_ids"] = ["ev_review"]  # type: ignore[index]

    with pytest.raises(CompetitorSynthesisValidationError) as exc_info:
        _validate(payload)

    assert exc_info.value.details["wrong_dimension_evidence_ids"] == ["ev_review"]


def test_validator_rejects_product_lineage_mismatch() -> None:
    context = _context()
    context.items[0].product = "Other Doorbell"

    with pytest.raises(CompetitorSynthesisValidationError) as exc_info:
        CompetitorSynthesisOutputValidator().validate(
            artifact_id="artifact_synthesis",
            task_id="task_synthesis",
            product_scope=[PRODUCT],
            requests=_requests(),
            specialist_artifacts=_artifacts(),
            evidence_context=context,
            output=CompetitorSynthesisModelOutput.model_validate(_output_dict()),
        )

    assert exc_info.value.details["wrong_product_evidence_ids"] == ["ev_official"]
