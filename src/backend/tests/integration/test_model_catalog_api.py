import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def model_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("TEST_MODEL_KEY", "unit-test-credential")
    catalog = json.dumps(
        [
            {
                "model_id": "test:model-a",
                "provider": "test",
                "provider_model": "provider-model-a",
                "display_name": "Test Model A",
                "credential_env": "TEST_MODEL_KEY",
                "capabilities": ["text", "structured_output"],
                "input_cost_microusd_per_million_tokens": 100000,
                "output_cost_microusd_per_million_tokens": 200000,
            }
        ]
    )
    settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'models.db'}",
        auto_create_schema=True,
        model_catalog_json=catalog,
        default_model_id="test:model-a",
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_model_api_returns_picker_data_without_credentials(
    model_client: TestClient,
) -> None:
    response = model_client.get("/api/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default_model_id"] == "test:model-a"
    assert body["items"][0]["model_id"] == "test:model-a"
    assert body["items"][0]["credential_available"] is True
    serialized = response.text
    assert "TEST_MODEL_KEY" not in serialized
    assert "unit-test-credential" not in serialized
