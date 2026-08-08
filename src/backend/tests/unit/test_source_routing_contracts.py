import pytest
from pydantic import ValidationError

from app.schemas.evidence import EvidenceClaimType
from app.schemas.source_routing import (
    SourceRouteTarget,
    SourceRoutingDecision,
    SourceRoutingDecisionAction,
    SourceRoutingModelOutput,
    SourceRoutingSelection,
    SourceRoutingSuggestedBy,
    SourceRoutingSuggestion,
)


def _suggestion() -> SourceRoutingSuggestion:
    return SourceRoutingSuggestion(
        route=SourceRouteTarget.PRICE_CHANNEL,
        claim_types=[
            EvidenceClaimType.PRICE_OBSERVATION,
            EvidenceClaimType.CHANNEL_AVAILABILITY,
        ],
        confidence=0.94,
        reason="页面同时包含商品报价、币种和库存信息。",
        signals=["currency:usd", "availability:in_stock"],
        suggested_by=SourceRoutingSuggestedBy.MODEL,
    )


def test_routing_contract_accepts_multi_label_model_output() -> None:
    output = SourceRoutingModelOutput(
        suggestions=[
            _suggestion(),
            SourceRoutingSuggestion(
                route=SourceRouteTarget.OFFICIAL_PRODUCT,
                claim_types=[EvidenceClaimType.VENDOR_CLAIM],
                confidence=0.91,
                reason="来源为品牌产品页面。",
                signals=["official_product_path"],
                suggested_by=SourceRoutingSuggestedBy.MODEL,
            ),
        ]
    )

    assert [item.route for item in output.suggestions] == [
        SourceRouteTarget.PRICE_CHANNEL,
        SourceRouteTarget.OFFICIAL_PRODUCT,
    ]


def test_routing_contract_rejects_duplicate_routes_and_claim_types() -> None:
    with pytest.raises(ValidationError, match="unique"):
        SourceRoutingModelOutput(suggestions=[_suggestion(), _suggestion()])

    with pytest.raises(ValidationError, match="unique"):
        SourceRoutingSuggestion(
            route=SourceRouteTarget.PRICE_CHANNEL,
            claim_types=[
                EvidenceClaimType.PRICE_OBSERVATION,
                EvidenceClaimType.PRICE_OBSERVATION,
            ],
            confidence=0.9,
            reason="重复分类不合法。",
            suggested_by=SourceRoutingSuggestedBy.MODEL,
        )


def test_routing_decision_requires_confirmed_selection_or_empty_rejection() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        SourceRoutingDecision(
            action=SourceRoutingDecisionAction.CONFIRM,
            selections=[],
            actor="reviewer",
            reason="确认路由。",
        )

    with pytest.raises(ValidationError, match="cannot include"):
        SourceRoutingDecision(
            action=SourceRoutingDecisionAction.REJECT,
            selections=[
                SourceRoutingSelection(
                    route=SourceRouteTarget.PRICE_CHANNEL,
                    claim_types=[EvidenceClaimType.PRICE_OBSERVATION],
                )
            ],
            actor="reviewer",
            reason="拒绝建议。",
        )
