from pathlib import Path

import yaml

from app.main import create_app
from app.workflows.contracts import (
    ResearchAgentType,
    ResearchHandoff,
    ResearchHandoffStatus,
)


def test_product_technical_routes_and_schemas_are_removed_from_public_contract() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    document = yaml.safe_load(
        (repository_root / "docs" / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )

    paths = document["paths"]
    schemas = document["components"]["schemas"]
    assert not any("product-technical" in path for path in paths)
    assert not any(name.startswith("ProductTechnical") for name in schemas)


def test_product_technical_routes_are_not_registered_in_fastapi() -> None:
    paths = {
        route.path
        for route in create_app().routes
        if hasattr(route, "path")
    }
    assert not any("product-technical" in path for path in paths)


def test_current_agent_types_only_expose_ecosystem_opportunity() -> None:
    values = {agent_type.value for agent_type in ResearchAgentType}
    assert "product_technical" not in values
    assert "ecosystem_opportunity" in values


def test_legacy_handoff_checkpoint_is_read_but_serialized_with_current_name() -> None:
    handoff = ResearchHandoff.model_validate(
        {
            "status": ResearchHandoffStatus.READY,
            "ready_for_product_technical": True,
        }
    )

    serialized = handoff.model_dump(mode="json")
    assert handoff.ready_for_ecosystem_opportunity is True
    assert serialized["ready_for_ecosystem_opportunity"] is True
    assert "ready_for_product_technical" not in serialized
