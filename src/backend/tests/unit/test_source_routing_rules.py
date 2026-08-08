from app.application.source_routing import DeterministicSourceRouter, SourceRoutingInput
from app.schemas.evidence import EvidenceClaimType
from app.schemas.source_routing import SourceRouteTarget


def _input(**updates: object) -> SourceRoutingInput:
    values: dict[str, object] = {
        "source_asset_id": "source_route_rules",
        "content_hash": "a" * 64,
        "display_name": "Product page",
        "source_url": "https://example.com/page",
        "media_type": "text/html",
        "media_category": "webpage",
        "authorization_basis": "publicly_available",
        "purpose": "automatic research classification",
        "fragment_hashes": ["b" * 64],
        "excerpts": ["General product information."],
    }
    values.update(updates)
    return SourceRoutingInput.model_validate(values)


def test_retail_page_routes_to_price_channel_without_model_facts() -> None:
    result = DeterministicSourceRouter().classify(
        _input(
            source_url="https://www.amazon.com/example/dp/ABC",
            excerpts=["$199.99. In stock. Save $20 with coupon."],
        )
    )

    price = next(
        item for item in result.suggestions if item.route is SourceRouteTarget.PRICE_CHANNEL
    )
    assert price.confidence >= 0.96
    assert set(price.claim_types) >= {
        EvidenceClaimType.PRICE_OBSERVATION,
        EvidenceClaimType.CHANNEL_AVAILABILITY,
        EvidenceClaimType.PROMOTION,
    }
    assert "retail_domain:amazon.com" in price.signals


def test_source_routing_is_multi_label_and_input_hash_is_stable() -> None:
    source = _input(
        source_url="https://brand.example/products/doorbell",
        purpose="官方产品规格和价格渠道研究",
        excerpts=["Specifications and compatibility. Price USD 199."],
    )
    result = DeterministicSourceRouter().classify(source)

    assert {item.route for item in result.suggestions} >= {
        SourceRouteTarget.OFFICIAL_PRODUCT,
        SourceRouteTarget.PRICE_CHANNEL,
        SourceRouteTarget.TECHNICAL_DOCUMENT,
    }
    assert source.stable_hash() == source.model_copy().stable_hash()
    assert (
        source.stable_hash() != source.model_copy(update={"purpose": "用户评价研究"}).stable_hash()
    )


def test_unknown_source_stays_unrouted_instead_of_guessing() -> None:
    result = DeterministicSourceRouter().classify(_input())

    assert result.suggestions == []
    assert result.signals == []
