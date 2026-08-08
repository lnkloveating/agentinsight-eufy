import pytest
from pydantic import ValidationError

from app.agents.competitor.official_product_contracts import (
    GapSeverity,
    OfficialFactType,
    OfficialProductFact,
    OfficialProductModelOutput,
    OfficialProductRecord,
    OfficialResearchGap,
)
from app.agents.competitor.official_product_validation import (
    OfficialProductOutputValidator,
    OfficialProductValidationError,
)
from app.integrations.a2a import CompetitorSpecialistType, EvidenceRequest
from app.workflows.contracts import (
    AgentEvidence,
    AgentEvidenceContext,
    ResearchTaskStatus,
)


def _request() -> EvidenceRequest:
    return EvidenceRequest(
        request_id="request_official",
        project_id="project_official",
        parent_task_id="task_competitor",
        specialist_type=CompetitorSpecialistType.OFFICIAL_PRODUCT,
        research_questions=["Extract supported official capabilities."],
        product_scope=["Target Doorbell"],
        region="US",
        evidence_types=["official_product_page"],
        allowed_claim_types=["vendor_claim", "fact"],
        minimum_independent_domains=1,
    )


def _evidence_context() -> AgentEvidenceContext:
    return AgentEvidenceContext(
        items=[
            AgentEvidence(
                evidence_id="ev_official",
                title="Official page",
                original_excerpt="Target Doorbell supports local package detection.",
                claim_type="vendor_claim",
                status="partially_verified",
                source_type="webpage",
                source_url="https://vendor.example/products/target",
                source_domain="vendor.example",
                product="Target Doorbell",
                region="US",
                confidence=0.9,
                authority_score=0.9,
                recency_score=0.8,
                diversity_score=0.5,
            )
        ],
        available_evidence_count=1,
        included_evidence_count=1,
        omitted_evidence_count=0,
        context_hash="a" * 64,
    )


def _output(evidence_id: str = "ev_official") -> OfficialProductModelOutput:
    return OfficialProductModelOutput(
        summary="官方资料声明该产品支持本地包裹检测。",
        summary_evidence_ids=[evidence_id],
        products=[
            OfficialProductRecord(
                scope_label="Target Doorbell",
                official_name="Target Doorbell",
                model_numbers=["MODEL-1"],
                evidence_ids=[evidence_id],
                facts=[
                    OfficialProductFact(
                        fact_id="fact_local_detection",
                        fact_type=OfficialFactType.CAPABILITY,
                        field_name="包裹检测",
                        value="支持本地处理",
                        qualifiers={"region": "US"},
                        confidence=0.9,
                        evidence_ids=[evidence_id],
                    )
                ],
                unknown_fields=["最低固件版本"],
            )
        ],
        contradictions=[],
        research_gaps=[
            OfficialResearchGap(
                scope_label="Target Doorbell",
                question="最低固件版本是什么？",
                reason="当前官方资料片段没有说明。",
                severity=GapSeverity.MEDIUM,
                recommended_source_types=["official_support_document"],
            )
        ],
        unknowns=["最低固件版本未知"],
    )


def test_completed_official_output_becomes_cited_specialist_artifact() -> None:
    artifact = OfficialProductOutputValidator().validate(
        a2a_task_id="a2a_official",
        request=_request(),
        evidence_context=_evidence_context(),
        output=_output(),
    )

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert artifact.evidence_ids == ["ev_official"]
    assert len(artifact.findings) == 2
    assert all(finding.evidence_ids == ["ev_official"] for finding in artifact.findings)
    assert artifact.structured_payload["schema_name"] == (
        "official_product_intelligence"
    )
    assert artifact.structured_payload["evidence_coverage"] == {
        "requested_product_count": 1,
        "represented_product_count": 1,
        "available_evidence_count": 1,
        "included_evidence_count": 1,
        "cited_evidence_count": 1,
        "independent_source_count": 1,
        "vendor_claim_count": 1,
        "fact_count": 0,
        "context_hash": "a" * 64,
    }


def test_official_validator_rejects_context_escape_and_scope_substitution() -> None:
    validator = OfficialProductOutputValidator()
    with pytest.raises(
        OfficialProductValidationError, match="未提供给模型"
    ) as unsupported:
        validator.validate(
            a2a_task_id="a2a_official",
            request=_request(),
            evidence_context=_evidence_context(),
            output=_output("ev_outside"),
        )
    assert unsupported.value.details == {
        "unsupported_evidence_ids": ["ev_outside"]
    }

    substituted = _output().model_copy(
        update={
            "products": [
                _output().products[0].model_copy(
                    update={"scope_label": "Different Product"}
                )
            ]
        }
    )
    with pytest.raises(OfficialProductValidationError, match="范围外"):
        validator.validate(
            a2a_task_id="a2a_official",
            request=_request(),
            evidence_context=_evidence_context(),
            output=substituted,
        )


def test_missing_product_scope_is_partial_and_empty_context_is_blocked() -> None:
    validator = OfficialProductOutputValidator()
    partial_output = _output().model_copy(update={"products": []})
    partial = validator.validate(
        a2a_task_id="a2a_official",
        request=_request(),
        evidence_context=_evidence_context(),
        output=partial_output,
    )
    empty_context = AgentEvidenceContext(
        items=[],
        available_evidence_count=0,
        included_evidence_count=0,
        omitted_evidence_count=0,
        context_hash="b" * 64,
    )
    blocked = validator.build_blocked(
        a2a_task_id="a2a_official",
        request=_request(),
        evidence_context=empty_context,
    )

    assert partial.status is ResearchTaskStatus.PARTIAL
    assert blocked.status is ResearchTaskStatus.BLOCKED
    assert blocked.findings == []
    assert blocked.evidence_ids == []
    assert blocked.errors == ["OFFICIAL_PRODUCT_EVIDENCE_REQUIRED"]


def test_model_contract_rejects_duplicate_product_and_fact_identifiers() -> None:
    product = _output().products[0]
    with pytest.raises(ValidationError, match="fact_ids must be unique"):
        OfficialProductRecord(
            scope_label=product.scope_label,
            official_name=product.official_name,
            evidence_ids=product.evidence_ids,
            facts=[product.facts[0], product.facts[0]],
        )

    with pytest.raises(ValidationError, match="scope_label must be unique"):
        OfficialProductModelOutput(
            summary="Summary",
            summary_evidence_ids=["ev_official"],
            products=[product, product],
        )

