from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_runtime_catalog_reports_unavailable_without_leaking_configuration(
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}",
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        external_runtime_workspace_root=str(tmp_path / "runtime"),
        opencode_executable="agentinsight-opencode-missing-for-test",
        opencode_credential_env="PRIVATE_RUNTIME_KEY",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/runtimes")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "items": [
            {
                "runtime_id": "opencode",
                "display_name": "OpenCode",
                "adapter_type": "external_cli",
                "capabilities": ["text", "structured_output", "local_files"],
                "enabled": True,
                "executable_available": False,
                "credential_available": False,
                "available": False,
                "version": None,
                "unavailable_reason": "executable_missing",
                "model_id": "anker-router/hackathon/v_model/glm-5.2",
            }
        ]
    }
    serialized = response.text
    assert "PRIVATE_RUNTIME_KEY" not in serialized
    assert str(tmp_path) not in serialized
