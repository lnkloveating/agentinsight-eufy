import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.events import ProjectEventBroker
from app.application.model_gateway import EnvironmentCredentialResolver
from app.application.runtime import (
    AgentRegistry,
    AgentRuntimeGateway,
    ExternalCliAgentAdapter,
    ExternalCliProcessRunner,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.application.runtime.cli_contracts import CliCommand, CliWorkspace
from app.application.runtime.contracts import AgentInvocation
from app.infrastructure.database import Database
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.project import ProjectStatus, ResearchBrief
from app.schemas.runtime import RuntimeCapability
from app.workflows.contracts import AgentContext, ResearchAgentType, ResearchTask
from tests.research_brief import home_safety_brief


class PythonArtifactDriver:
    runtime_id = "python-contract-fixture"
    display_name = "Python Contract Fixture"
    adapter_type = "external_cli"
    enabled = True
    executable = sys.executable
    credential_env = "TEST_EXTERNAL_CLI_KEY"
    model_id = None
    capabilities = (
        RuntimeCapability.TEXT,
        RuntimeCapability.STRUCTURED_OUTPUT,
        RuntimeCapability.LOCAL_FILES,
    )

    def __init__(self, *, exit_with_secret: bool = False) -> None:
        self.exit_with_secret = exit_with_secret

    def version_arguments(self) -> tuple[str, ...]:
        return ("--version",)

    def prepare(
        self,
        invocation: AgentInvocation,
        workspace: CliWorkspace,
        credential: str,
    ) -> CliCommand:
        del invocation
        if self.exit_with_secret:
            program = (
                "import os,sys; "
                "sys.stderr.write('failure:' + os.environ['TEST_EXTERNAL_CLI_KEY']); "
                "raise SystemExit(7)"
            )
        else:
            program = (
                "import json,os; "
                "assert os.environ['TEST_EXTERNAL_CLI_KEY']=='runtime-only-secret'; "
                "data=json.load(open('input/invocation.json',encoding='utf-8')); "
                "task=data['task']; "
                "artifact={'artifact_id':'external-result','task_id':task['task_id'],"
                "'artifact_type':task['agent_type'],'status':'blocked','payload':{},"
                "'evidence_ids':[],'contradictions':[],"
                "'unknowns':['Evidence processing is not bound yet.'],"
                "'quality_score':0,'errors':[]}; "
                "print(json.dumps(artifact))"
            )
        return CliCommand(
            executable=self.executable,
            arguments=("-c", program),
            environment={self.credential_env: credential},
        )

    def decode_output(self, stdout: bytes) -> object:
        return json.loads(stdout)


def _brief() -> ResearchBrief:
    return home_safety_brief()


async def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'external-cli.db'}")
    await database.create_schema()
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            ProjectModel(
                project_id="proj_external_cli",
                status=ProjectStatus.RESEARCHING,
                current_stage="external_cli_test",
                progress=20,
                brief_json=_brief().model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    return database


def _task(task_id: str) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        project_id="proj_external_cli",
        agent_type=ResearchAgentType.USER_RESEARCH,
        goal="Use the authorized local invocation only.",
        budget={"deadline_seconds": 5},
    )


def _context() -> AgentContext:
    return AgentContext(
        project_id="proj_external_cli",
        brief=_brief(),
        iteration=0,
    )


def _adapter(driver: PythonArtifactDriver, runtime_root: Path) -> ExternalCliAgentAdapter:
    return ExternalCliAgentAdapter(
        driver,
        EnvironmentCredentialResolver(
            {"TEST_EXTERNAL_CLI_KEY": "runtime-only-secret"}
        ),
        ExternalCliProcessRunner(max_output_bytes=65_536, probe_timeout_seconds=2),
        runtime_root,
    )


@pytest.mark.asyncio
async def test_external_cli_adapter_runs_real_process_and_persists_artifact(
    tmp_path: Path,
) -> None:
    database = await _database(tmp_path)
    runtime_root = tmp_path / "runtime"
    agents = AgentRegistry()
    agents.bind(
        ResearchAgentType.USER_RESEARCH,
        _adapter(PythonArtifactDriver(), runtime_root),
    )
    gateway = AgentRuntimeGateway(
        database, agents, ProjectEventBroker(), "trace_external_cli"
    )
    try:
        artifact = await gateway.execute(_task("task_external_success"), _context())

        assert artifact.status == "blocked"
        assert artifact.unknowns == ["Evidence processing is not bound yet."]
        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_external_cli")
        assert len(runs) == 1
        assert runs[0].adapter_type == "external_cli"
        assert runs[0].status == "blocked"

        files = [path for path in runtime_root.rglob("*") if path.is_file()]
        assert {path.name for path in files} == {
            "invocation.json",
            "process.json",
            "research_artifact.json",
        }
        assert all("runtime-only-secret" not in path.read_text(encoding="utf-8") for path in files)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_external_cli_adapter_redacts_process_failure_and_saves_no_artifact(
    tmp_path: Path,
) -> None:
    database = await _database(tmp_path)
    runtime_root = tmp_path / "runtime"
    agents = AgentRegistry()
    agents.bind(
        ResearchAgentType.USER_RESEARCH,
        _adapter(PythonArtifactDriver(exit_with_secret=True), runtime_root),
    )
    gateway = AgentRuntimeGateway(
        database, agents, ProjectEventBroker(), "trace_external_failure"
    )
    try:
        with pytest.raises(RuntimeGatewayError) as captured:
            await gateway.execute(_task("task_external_failure"), _context())

        assert captured.value.code is RuntimeErrorCode.PROCESS_FAILED
        assert captured.value.details["exit_code"] == 7
        assert "runtime-only-secret" not in json.dumps(captured.value.details)
        assert captured.value.details["stderr"] == "failure:***"
        assert not list(runtime_root.rglob("research_artifact.json"))
        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_external_cli")
        assert runs[0].status == "failed"
        assert runs[0].error_code == RuntimeErrorCode.PROCESS_FAILED
    finally:
        await database.dispose()
