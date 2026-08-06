import json

import pytest

from app.application.model_gateway import (
    EnvironmentCredentialResolver,
    ModelCatalog,
    ModelCatalogError,
)


def _catalog_json() -> str:
    return json.dumps(
        [
            {
                "model_id": "provider:model-a",
                "provider": "provider",
                "provider_model": "model-a-internal",
                "display_name": "Model A",
                "credential_env": "PROVIDER_A_KEY",
                "capabilities": ["text", "structured_output", "text"],
                "context_window": 1000,
            },
            {
                "model_id": "provider:model-b",
                "provider": "provider",
                "provider_model": "model-b-internal",
                "display_name": "Model B",
                "credential_env": "PROVIDER_B_KEY",
                "enabled": False,
            },
        ]
    )


def test_catalog_exposes_safe_enabled_models_and_available_default() -> None:
    catalog = ModelCatalog.from_json(
        _catalog_json(), default_model_id="provider:model-a"
    )
    credentials = EnvironmentCredentialResolver(
        {"PROVIDER_A_KEY": "unit-test-credential", "PROVIDER_B_KEY": ""}
    )

    page = catalog.public_page(credentials)

    assert page.default_model_id == "provider:model-a"
    assert len(page.items) == 1
    assert page.items[0].model_id == "provider:model-a"
    assert page.items[0].credential_available is True
    assert [item.value for item in page.items[0].capabilities] == [
        "text",
        "structured_output",
    ]
    payload = page.model_dump(mode="json")
    assert "credential_env" not in str(payload)
    assert "unit-test-credential" not in str(payload)


def test_catalog_rejects_duplicates_and_unknown_default() -> None:
    definition = json.loads(_catalog_json())[0]
    with pytest.raises(ModelCatalogError, match="duplicate model id"):
        ModelCatalog.from_json(json.dumps([definition, definition]))
    with pytest.raises(ModelCatalogError, match="default model is not configured"):
        ModelCatalog.from_json(_catalog_json(), default_model_id="provider:missing")


def test_missing_credential_removes_default_but_keeps_model_visible() -> None:
    catalog = ModelCatalog.from_json(
        _catalog_json(), default_model_id="provider:model-a"
    )
    page = catalog.public_page(EnvironmentCredentialResolver({}))

    assert page.default_model_id is None
    assert page.items[0].credential_available is False
