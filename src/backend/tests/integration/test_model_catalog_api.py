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


def test_project_persists_selected_model_and_run_audit_fields(
    model_client: TestClient,
) -> None:
    response = model_client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "哪些家庭事件值得进一步研究？",
                "category": "家庭安防",
                "target_user": "北美家庭用户",
                "region": "北美",
            },
            "model_selection": {
                "default_model_id": "test:model-a",
                "agent_overrides": {"red_team": "test:model-a"},
            },
        },
    )

    assert response.status_code == 201
    project = response.json()
    assert project["model_selection"] == {
        "default_model_id": "test:model-a",
        "agent_overrides": {"red_team": "test:model-a"},
    }
    runs = model_client.get(
        f"/api/v1/projects/{project['project_id']}/agents"
    ).json()
    assert runs[0]["model_id"] == "test:model-a"
    assert runs[0]["model_provider"] == "test"
    assert runs[0]["input_tokens"] == 0
    assert runs[0]["estimated_cost_microusd"] == 0


def test_project_rejects_unknown_model_and_agent_override(
    model_client: TestClient,
) -> None:
    brief = {
        "question": "哪些家庭事件值得进一步研究？",
        "category": "家庭安防",
        "target_user": "北美家庭用户",
        "region": "北美",
    }
    unknown_model = model_client.post(
        "/api/v1/projects",
        json={
            "brief": brief,
            "model_selection": {"default_model_id": "test:missing"},
        },
    )
    invalid_agent = model_client.post(
        "/api/v1/projects",
        json={
            "brief": brief,
            "model_selection": {
                "default_model_id": "test:model-a",
                "agent_overrides": {"unknown_agent": "test:model-a"},
            },
        },
    )

    assert unknown_model.status_code == 422
    assert unknown_model.json()["code"] == "MODEL_NOT_FOUND"
    assert invalid_agent.status_code == 422
    assert invalid_agent.json()["code"] == "MODEL_AGENT_OVERRIDE_INVALID"
