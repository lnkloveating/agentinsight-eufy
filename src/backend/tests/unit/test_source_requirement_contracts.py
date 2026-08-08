import pytest
from pydantic import ValidationError

from app.schemas.source_requirements import SourceRequirementScopeUpdate


def test_scope_allows_unresolved_models_but_rejects_duplicates_and_overlap() -> None:
    unresolved = SourceRequirementScopeUpdate(
        target_products=[{"brand": " eufy ", "model": "E340"}],
        competitors=[{"brand": "Ring", "model": None}],
        dimensions=["official_product", "price_channel"],
        actor=" lead ",
        reason=" confirm scope ",
    )

    assert unresolved.target_products[0].brand == "eufy"
    assert unresolved.competitors[0].model is None
    assert unresolved.actor == "lead"

    with pytest.raises(ValidationError, match="products must be unique"):
        SourceRequirementScopeUpdate(
            target_products=[
                {"brand": "eufy", "model": "E340"},
                {"brand": "EUFY", "model": "e340"},
            ],
            competitors=[],
            dimensions=["official_product"],
            actor="lead",
            reason="duplicate",
        )

    with pytest.raises(ValidationError, match="both target and competitor"):
        SourceRequirementScopeUpdate(
            target_products=[{"brand": "eufy", "model": "E340"}],
            competitors=[{"brand": "EUFY", "model": "e340"}],
            dimensions=["official_product"],
            actor="lead",
            reason="overlap",
        )


def test_scope_rejects_duplicate_dimensions_and_variant_without_model() -> None:
    with pytest.raises(ValidationError, match="dimensions must be unique"):
        SourceRequirementScopeUpdate(
            dimensions=["official_product", "official_product"],
            actor="lead",
            reason="duplicate dimensions",
        )

    with pytest.raises(ValidationError, match="variant requires an exact model"):
        SourceRequirementScopeUpdate(
            target_products=[{"brand": "eufy", "variant": "black"}],
            dimensions=["official_product"],
            actor="lead",
            reason="invalid product",
        )
