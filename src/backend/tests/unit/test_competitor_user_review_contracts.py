from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.agents.competitor.user_review_contracts import (
    CompetitorUserReviewModelOutput,
    ReviewRecurrenceStatus,
    ReviewSampleLimitation,
    ReviewSentiment,
    ReviewThemeDraft,
)
from app.agents.competitor.user_review_validation import (
    CompetitorUserReviewOutputValidator,
    CompetitorUserReviewValidationError,
)
from app.integrations.a2a import CompetitorSpecialistType, EvidenceRequest
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext, ResearchTaskStatus


def _request(*, minimum_domains: int = 2) -> EvidenceRequest:
    return EvidenceRequest(
        request_id="request_review",
        project_id="project_review",
        parent_task_id="task_competitor",
        specialist_type=CompetitorSpecialistType.USER_REVIEW,
        research_questions=["Identify recurring user opinions and sample limitations."],
        product_scope=["Target Doorbell"],
        region="US",
        evidence_types=["authorized_user_review", "authorized_research_file"],
        allowed_claim_types=["user_opinion"],
        minimum_independent_domains=minimum_domains,
    )


def _evidence(
    evidence_id: str,
    domain: str,
    excerpt: str,
    *,
    claim_type: str = "user_opinion",
    product: str = "Target Doorbell",
    region: str | None = "US",
) -> AgentEvidence:
    return AgentEvidence(
        evidence_id=evidence_id,
        title=f"Review {evidence_id}",
        original_excerpt=excerpt,
        claim_type=claim_type,
        status="partially_verified",
        source_type="webpage",
        source_url=f"https://{domain}/reviews/target-doorbell",
        source_domain=domain,
        product=product,
        region=region,
        user_segment="doorbell owner",
        collected_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        confidence=0.85,
        authority_score=0.7,
        recency_score=0.8,
        diversity_score=0.8,
    )


def _context(*, second_claim_type: str = "user_opinion") -> AgentEvidenceContext:
    items = [
        _evidence(
            "ev_review_a",
            "reviews-a.example",
            "Package alerts are often delayed after delivery.",
        ),
        _evidence(
            "ev_review_b",
            "reviews-b.example",
            "The notification arrived late after my parcel was left outside.",
            claim_type=second_claim_type,
        ),
    ]
    return AgentEvidenceContext(
        items=items,
        available_evidence_count=2,
        included_evidence_count=2,
        omitted_evidence_count=0,
        context_hash="a" * 64,
    )


def _output(evidence_ids: list[str] | None = None) -> CompetitorUserReviewModelOutput:
    citations = evidence_ids or ["ev_review_a", "ev_review_b"]
    return CompetitorUserReviewModelOutput(
        summary="两条独立来源的用户表达都涉及包裹通知延迟。",
        summary_evidence_ids=citations,
        review_themes=[
            ReviewThemeDraft(
                theme_id="theme_delayed_package_alert",
                scope_label="Target Doorbell",
                theme="包裹通知延迟",
                sentiment=ReviewSentiment.NEGATIVE,
                user_expression="用户表示包裹送达后通知到达较晚。",
                event_context="包裹已放在门外之后",
                user_impact="用户不能及时处理门外包裹。",
                user_segment="doorbell owner",
                region="US",
                confidence=0.86,
                evidence_ids=citations,
            )
        ],
        contradictions=[],
        sample_limitations=[
            ReviewSampleLimitation(
                scope_label="Target Doorbell",
                description="当前只有两个公开评论来源。",
                impact="不能推断总体用户中的发生比例。",
                evidence_ids=citations,
            )
        ],
        research_gaps=[],
        unknowns=["总体发生率未知"],
    )


def test_repeated_cross_source_theme_becomes_completed_cited_artifact() -> None:
    artifact = CompetitorUserReviewOutputValidator().validate(
        a2a_task_id="a2a_review",
        request=_request(),
        evidence_context=_context(),
        output=_output(),
    )

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert artifact.evidence_ids == ["ev_review_a", "ev_review_b"]
    assert len(artifact.findings) == 1
    theme = artifact.structured_payload["review_themes"][0]
    assert theme["support_count"] == 2
    assert theme["independent_source_count"] == 2
    assert theme["recurrence_status"] == ReviewRecurrenceStatus.REPEATED_ACROSS_SOURCES
    assert artifact.structured_payload["evidence_coverage"]["repeated_theme_count"] == 1


def test_single_report_is_preserved_but_cannot_complete() -> None:
    artifact = CompetitorUserReviewOutputValidator().validate(
        a2a_task_id="a2a_review",
        request=_request(minimum_domains=1),
        evidence_context=_context(),
        output=_output(["ev_review_a"]),
    )

    assert artifact.status is ResearchTaskStatus.PARTIAL
    theme = artifact.structured_payload["review_themes"][0]
    assert theme["recurrence_status"] == ReviewRecurrenceStatus.SINGLE_REPORT
    assert theme["support_count"] == 1


def test_validator_rejects_evidence_escape_wrong_product_and_claim_type() -> None:
    validator = CompetitorUserReviewOutputValidator()
    with pytest.raises(CompetitorUserReviewValidationError, match="未提供给模型"):
        validator.validate(
            a2a_task_id="a2a_review",
            request=_request(),
            evidence_context=_context(),
            output=_output(["ev_outside"]),
        )

    wrong_product_context = _context().model_copy(
        update={
            "items": [
                _context().items[0].model_copy(update={"product": "Other Doorbell"}),
                _context().items[1],
            ]
        }
    )
    with pytest.raises(CompetitorUserReviewValidationError, match="产品血缘不匹配"):
        validator.validate(
            a2a_task_id="a2a_review",
            request=_request(),
            evidence_context=wrong_product_context,
            output=_output(),
        )

    with pytest.raises(CompetitorUserReviewValidationError, match="非 user_opinion"):
        validator.validate(
            a2a_task_id="a2a_review",
            request=_request(),
            evidence_context=_context(second_claim_type="vendor_claim"),
            output=_output(),
        )


def test_empty_context_is_blocked_and_duplicate_theme_id_is_rejected() -> None:
    empty = AgentEvidenceContext(
        items=[],
        available_evidence_count=0,
        included_evidence_count=0,
        omitted_evidence_count=0,
        context_hash="b" * 64,
    )
    blocked = CompetitorUserReviewOutputValidator().build_blocked(
        a2a_task_id="a2a_review", request=_request(), evidence_context=empty
    )
    assert blocked.status is ResearchTaskStatus.BLOCKED
    assert blocked.errors == ["COMPETITOR_USER_REVIEW_EVIDENCE_REQUIRED"]

    theme = _output().review_themes[0]
    with pytest.raises(ValidationError, match="theme_id must be unique"):
        CompetitorUserReviewModelOutput(
            summary="Summary",
            summary_evidence_ids=["ev_review_a"],
            review_themes=[theme, theme],
        )
