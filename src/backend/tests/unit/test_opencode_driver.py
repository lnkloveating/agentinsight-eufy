import json
from pathlib import Path

from app.application.runtime import AgentInvocation, CancellationToken, OpenCodeCliDriver
from app.application.runtime.external_workspace import ExternalCliWorkspaceManager
from app.schemas.runtime import RuntimeCapability
from app.workflows.contracts import AgentContext, ResearchAgentType, ResearchTask
from tests.research_brief import home_safety_brief


def _invocation(project_id: str = "proj_driver") -> AgentInvocation:
    return AgentInvocation(
        agent_run_id="run_driver",
        trace_id="trace_driver",
        attempt_number=1,
        workspace_key="workspace_driver",
        input_artifact_ids=(),
        task=ResearchTask(
            task_id="task_driver",
            project_id=project_id,
            agent_type=ResearchAgentType.USER_RESEARCH,
            goal="Analyze only authorized local material.",
        ),
        context=AgentContext(
            project_id=project_id,
            brief=home_safety_brief(),
            iteration=0,
        ),
        cancellation_token=CancellationToken(),
    )


def _driver() -> OpenCodeCliDriver:
    return OpenCodeCliDriver(
        executable="opencode",
        provider_id="test-router",
        provider_name="Test Router",
        provider_base_url="https://router.example.com",
        provider_model="model/test-one",
        credential_env="TEST_ROUTER_KEY",
    )


def _artifact() -> dict[str, object]:
    return {
        "artifact_id": "artifact_driver",
        "task_id": "task_driver",
        "artifact_type": "user_research",
        "status": "blocked",
        "payload": {},
        "evidence_ids": [],
        "contradictions": [],
        "unknowns": ["No validated evidence yet."],
        "quality_score": 0,
        "errors": [],
    }


def test_opencode_driver_creates_secret_free_read_only_configuration(
    tmp_path: Path,
) -> None:
    invocation = _invocation()
    workspace = ExternalCliWorkspaceManager(tmp_path).prepare(invocation)
    command = _driver().prepare(invocation, workspace, "local-test-secret")
    config_text = (workspace.state_dir / "opencode.json").read_text(encoding="utf-8")
    config = json.loads(config_text)

    assert "local-test-secret" not in config_text
    assert config["provider"]["test-router"]["options"]["apiKey"] == (
        "{env:TEST_ROUTER_KEY}"
    )
    assert config["permission"]["read"] == "allow"
    assert config["permission"]["bash"] == "deny"
    assert config["permission"]["edit"] == "deny"
    assert config["permission"]["external_directory"] == "deny"
    assert config["permission"]["webfetch"] == "deny"
    assert command.environment["TEST_ROUTER_KEY"] == "local-test-secret"
    assert command.arguments[:4] == ("--pure", "run", "--format", "json")
    assert _driver().capabilities == (
        RuntimeCapability.TEXT,
        RuntimeCapability.STRUCTURED_OUTPUT,
        RuntimeCapability.LOCAL_FILES,
    )


def test_opencode_driver_decodes_direct_and_json_event_output() -> None:
    driver = _driver()
    artifact = _artifact()
    direct = driver.decode_output(json.dumps(artifact).encode())
    event = {
        "type": "text",
        "part": {
            "type": "text",
            "text": "```json\n" + json.dumps(artifact) + "\n```",
        },
    }

    assert direct == artifact
    assert driver.decode_output((json.dumps(event) + "\n").encode()) == artifact


def test_workspace_hashes_unsafe_identifiers_and_contains_only_invocation(
    tmp_path: Path,
) -> None:
    workspace = ExternalCliWorkspaceManager(tmp_path).prepare(_invocation("../unsafe"))

    assert workspace.root.is_relative_to(tmp_path.resolve())
    assert workspace.root.parent.name.startswith("id_")
    assert [path.name for path in workspace.input_dir.iterdir()] == ["invocation.json"]
    payload = json.loads(workspace.invocation_path.read_text(encoding="utf-8"))
    assert payload["output_schema"]["title"] == "ResearchArtifact"
