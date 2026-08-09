import pytest
from pydantic import ValidationError

from app.application.competitor_material_discovery import (
    CompetitorMaterialDiscoveryService,
)
from app.schemas.competitor_material_discovery import (
    CompetitorMaterialDecisionCreate,
    CompetitorMaterialDiscoveryCreate,
)
from app.schemas.source_requirements import CompetitorResearchDimension, ProductReference


def test_material_queries_are_deterministic_and_dimension_specific() -> None:
    product = ProductReference(brand="Ring", model="Battery Doorbell Pro")

    assert CompetitorMaterialDiscoveryService.build_query(
        product, CompetitorResearchDimension.OFFICIAL_PRODUCT, "US"
    ) == (
        "Ring Battery Doorbell Pro official product specifications features "
        "compatibility manual"
    )
    assert CompetitorMaterialDiscoveryService.build_query(
        product, CompetitorResearchDimension.PRICE_CHANNEL, "US"
    ) == "Ring Battery Doorbell Pro price availability authorized retailer US"
    assert CompetitorMaterialDiscoveryService.build_query(
        product, CompetitorResearchDimension.USER_REVIEW, "US"
    ) == "Ring Battery Doorbell Pro user reviews owner feedback problems experience"


def test_material_create_rejects_duplicate_products_and_dimensions() -> None:
    base = {
        "products": [
            {
                "product_role": "competitor",
                "product": {"brand": "Ring", "model": "Battery Doorbell Pro"},
            }
        ],
        "dimensions": ["official_product"],
        "provider_id": "test-search",
        "max_results_per_query": 5,
        "requested_by": "lead",
        "purpose": "Find research material.",
    }
    with pytest.raises(ValidationError):
        CompetitorMaterialDiscoveryCreate.model_validate(
            {**base, "products": [*base["products"], *base["products"]]}
        )
    with pytest.raises(ValidationError):
        CompetitorMaterialDiscoveryCreate.model_validate(
            {**base, "dimensions": ["official_product", "official_product"]}
        )


def test_material_decision_enforces_selection_and_public_authorization() -> None:
    with pytest.raises(ValidationError):
        CompetitorMaterialDecisionCreate.model_validate(
            {
                "action": "confirm",
                "selected_candidate_ids": ["candidate_1"],
                "authorization_basis": None,
                "authorization_confirmed": False,
                "actor": "lead",
                "reason": "Use this source.",
            }
        )
    with pytest.raises(ValidationError):
        CompetitorMaterialDecisionCreate.model_validate(
            {
                "action": "reject",
                "selected_candidate_ids": ["candidate_1"],
                "authorization_basis": None,
                "authorization_confirmed": False,
                "actor": "lead",
                "reason": "Reject this batch.",
            }
        )
