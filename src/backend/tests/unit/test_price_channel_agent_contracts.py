from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.agents.competitor.price_channel_contracts import (
    ChannelAvailabilityStatus,
    ChannelObservationDraft,
    PriceChannelModelOutput,
    PriceKind,
    PriceObservationDraft,
)
from app.agents.competitor.price_channel_validation import (
    PriceChannelOutputValidator,
    PriceChannelValidationError,
)
from app.integrations.a2a import CompetitorSpecialistType, EvidenceRequest
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext, ResearchTaskStatus

OBSERVED_AT = datetime(2026, 8, 9, 10, 30, tzinfo=UTC)


def _request(*, minimum_domains: int = 2) -> EvidenceRequest:
    return EvidenceRequest(
        request_id="request_price",
        project_id="project_price",
        parent_task_id="task_competitor",
        specialist_type=CompetitorSpecialistType.PRICE_CHANNEL,
        research_questions=["Extract time-bounded price and channel observations."],
        product_scope=["Target Doorbell"],
        region="US",
        evidence_types=["official_store_page", "authorized_channel_page"],
        allowed_claim_types=[
            "price_observation",
            "channel_availability",
            "seller_information",
            "promotion",
        ],
        minimum_independent_domains=minimum_domains,
    )


def _evidence(
    evidence_id: str,
    claim_type: str,
    domain: str,
    *,
    product: str = "Target Doorbell",
    region: str = "US",
    collected_at: datetime | None = OBSERVED_AT,
) -> AgentEvidence:
    return AgentEvidence(
        evidence_id=evidence_id,
        title=f"Price evidence {evidence_id}",
        original_excerpt="Target Doorbell is listed for USD 149.99 and is in stock.",
        claim_type=claim_type,
        status="partially_verified",
        source_type="webpage",
        source_url=f"https://{domain}/target-doorbell",
        source_domain=domain,
        product=product,
        region=region,
        collected_at=collected_at,
        confidence=0.9,
        authority_score=0.85,
        recency_score=0.9,
        diversity_score=0.7,
    )


def _context(*, missing_time: bool = False) -> AgentEvidenceContext:
    items = [
        _evidence(
            "ev_price",
            "price_observation",
            "vendor.example",
            collected_at=None if missing_time else OBSERVED_AT,
        ),
        _evidence(
            "ev_channel",
            "channel_availability",
            "retailer.example",
            collected_at=None if missing_time else OBSERVED_AT,
        ),
    ]
    return AgentEvidenceContext(
        items=items,
        available_evidence_count=2,
        included_evidence_count=2,
        omitted_evidence_count=0,
        context_hash="a" * 64,
    )


def _output() -> PriceChannelModelOutput:
    return PriceChannelModelOutput(
        summary="两条授权渠道证据显示该产品存在时间化价格与库存观察。",
        summary_evidence_ids=["ev_price", "ev_channel"],
        price_observations=[
            PriceObservationDraft(
                observation_id="price_vendor_us",
                scope_label="Target Doorbell",
                amount="149.99",
                currency="USD",
                price_kind=PriceKind.REGULAR,
                region="US",
                channel_name="Vendor Store",
                seller_name="Vendor",
                variant="MODEL-1",
                confidence=0.9,
                evidence_ids=["ev_price"],
            )
        ],
        channel_observations=[
            ChannelObservationDraft(
                observation_id="channel_retailer_us",
                scope_label="Target Doorbell",
                channel_name="Authorized Retailer",
                seller_name="Retailer",
                region="US",
                availability=ChannelAvailabilityStatus.IN_STOCK,
                variant="MODEL-1",
                confidence=0.85,
                evidence_ids=["ev_channel"],
            )
        ],
        contradictions=[],
        research_gaps=[],
        unknowns=[],
    )


def test_completed_output_becomes_time_bounded_cited_artifact() -> None:
    artifact = PriceChannelOutputValidator().validate(
        a2a_task_id="a2a_price",
        request=_request(),
        evidence_context=_context(),
        output=_output(),
    )

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert artifact.evidence_ids == ["ev_channel", "ev_price"]
    assert len(artifact.findings) == 2
    assert all(finding.evidence_ids for finding in artifact.findings)
    payload = artifact.structured_payload
    assert payload["schema_name"] == "price_channel_intelligence"
    assert payload["price_observations"][0]["amount"] == "149.99"
    assert payload["price_observations"][0]["observed_to"] == "2026-08-09T10:30:00Z"
    assert payload["evidence_coverage"]["independent_source_count"] == 2


def test_validator_rejects_evidence_escape_product_region_and_missing_time() -> None:
    validator = PriceChannelOutputValidator()
    outside = _output().model_copy(
        update={
            "price_observations": [
                _output().price_observations[0].model_copy(
                    update={"evidence_ids": ["ev_outside"]}
                )
            ]
        }
    )
    with pytest.raises(PriceChannelValidationError, match="未提供给模型"):
        validator.validate(
            a2a_task_id="a2a_price",
            request=_request(),
            evidence_context=_context(),
            output=outside,
        )

    wrong_region = _output().model_copy(
        update={
            "price_observations": [
                _output().price_observations[0].model_copy(update={"region": "AU"})
            ]
        }
    )
    with pytest.raises(PriceChannelValidationError, match="地区不一致"):
        validator.validate(
            a2a_task_id="a2a_price",
            request=_request(),
            evidence_context=_context(),
            output=wrong_region,
        )

    wrong_product_context = _context().model_copy(
        update={
            "items": [
                _context().items[0].model_copy(update={"product": "Other Doorbell"}),
                _context().items[1],
            ]
        }
    )
    with pytest.raises(PriceChannelValidationError, match="产品或地区血缘不匹配"):
        validator.validate(
            a2a_task_id="a2a_price",
            request=_request(),
            evidence_context=wrong_product_context,
            output=_output(),
        )

    with pytest.raises(PriceChannelValidationError, match="采集时间"):
        validator.validate(
            a2a_task_id="a2a_price",
            request=_request(),
            evidence_context=_context(missing_time=True),
            output=_output(),
        )


def test_incomplete_coverage_is_partial_and_empty_context_is_blocked() -> None:
    validator = PriceChannelOutputValidator()
    partial_output = _output().model_copy(update={"channel_observations": []})
    partial = validator.validate(
        a2a_task_id="a2a_price",
        request=_request(),
        evidence_context=_context(),
        output=partial_output,
    )
    empty = AgentEvidenceContext(
        items=[],
        available_evidence_count=0,
        included_evidence_count=0,
        omitted_evidence_count=0,
        context_hash="b" * 64,
    )
    blocked = validator.build_blocked(
        a2a_task_id="a2a_price", request=_request(), evidence_context=empty
    )

    assert partial.status is ResearchTaskStatus.PARTIAL
    assert blocked.status is ResearchTaskStatus.BLOCKED
    assert blocked.errors == ["PRICE_CHANNEL_EVIDENCE_REQUIRED"]


def test_model_contract_rejects_bad_currency_amount_and_duplicate_ids() -> None:
    price = _output().price_observations[0]
    with pytest.raises(ValidationError):
        PriceObservationDraft.model_validate(
            {**price.model_dump(mode="python"), "amount": "0"}
        )
    with pytest.raises(ValidationError):
        PriceObservationDraft.model_validate(
            {**price.model_dump(mode="python"), "currency": "usd"}
        )
    with pytest.raises(ValidationError, match="observation_id must be unique"):
        PriceChannelModelOutput(
            summary="Summary",
            summary_evidence_ids=["ev_price"],
            price_observations=[price],
            channel_observations=[
                _output().channel_observations[0].model_copy(
                    update={"observation_id": price.observation_id}
                )
            ],
        )
