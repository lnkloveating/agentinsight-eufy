import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.events import ProjectEventBroker
from app.application.model_gateway import (
    EnvironmentCredentialResolver,
    ModelCatalog,
    ModelGateway,
    ModelProviderRegistry,
    ModelUsage,
    ProjectModelSelectionResolver,
    PromptDefinition,
    PromptRegistry,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.application.runtime import (
    AgentRegistry,
    AgentRuntimeGateway,
    InternalModelAgentAdapter,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.infrastructure.database import Database
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchTask,
)
from tests.research_brief import home_safety_brief


class ArtifactProvider:
    provider_id = "test"

    def __init__(self) -> None:
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        return ProviderModelResult(
            output={
                "artifact_id": "artifact_provider_output",
                "task_id": "task_user_model",
                "artifact_type": "user_research",
                "status": "blocked",
                "payload": {},
                "evidence_ids": [],
                "contradictions": [],
                "unknowns": ["No evidence connector is bound in this test."],
                "quality_score": 0,
                "errors": [],
            },
            usage=ModelUsage(input_tokens=12, output_tokens=8),
            provider_request_id="test-request",
        )


def _catalog() -> ModelCatalog:
    return ModelCatalog.from_json(
        json.dumps(
            [
                {
                    "model_id": "test:model-a",
                    "provider": "test",
                    "provider_model": "provider-model-a",
                    "display_name": "Model A",
                    "credential_env": "TEST_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                },
                {
                    "model_id": "test:model-b",
                    "provider": "test",
                    "provider_model": "provider-model-b",
                    "display_name": "Model B",
                    "credential_env": "TEST_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                },
            ]
        )
    )


def _brief() -> ResearchBrief:
    return home_safety_brief()


async def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'adapter.db'}")
    await database.create_schema()
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            ProjectModel(
                project_id="proj_adapter",
                status=ProjectStatus.RESEARCHING,
                current_stage="adapter_test",
                progress=10,
                brief_json=_brief().model_dump(mode="json"),
                model_selection_json={
                    "default_model_id": "test:model-a",
                    "agent_overrides": {"user_research": "test:model-b"},
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    return database


def _task(agent_type: ResearchAgentType, task_id: str) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        project_id="proj_adapter",
        agent_type=agent_type,
        goal="Verify the model adapter contract.",
    )


def _context() -> AgentContext:
    return AgentContext(
        project_id="proj_adapter",
        brief=_brief(),
        iteration=0,
    )


@pytest.mark.asyncio
async def test_internal_adapter_uses_agent_override_and_persists_model_audit(
    tmp_path: Path,
) -> None:
    database = await _database(tmp_path)
    provider = ArtifactProvider()
    providers = ModelProviderRegistry()
    providers.register(provider)
    model_gateway = ModelGateway(
        database,
        _catalog(),
        EnvironmentCredentialResolver({"TEST_MODEL_KEY": "unit-test-credential"}),
        providers,
        max_retries=0,
    )
    prompts = PromptRegistry()
    prompts.register(
        PromptDefinition(
            prompt_key="agent:user_research",
            version="1",
            system_template="Return {agent_type} as the required schema.",
            user_template="Task {task_id}: {goal}; brief={brief_json}",
        )
    )
    adapter = InternalModelAgentAdapter(
        model_gateway,
        prompts,
        ProjectModelSelectionResolver(database),
    )
    agents = AgentRegistry()
    agents.bind(ResearchAgentType.USER_RESEARCH, adapter)
    runtime = AgentRuntimeGateway(
        database,
        agents,
        ProjectEventBroker(),
        "trace_adapter",
    )
    try:
        artifact = await runtime.execute(
            _task(ResearchAgentType.USER_RESEARCH, "task_user_model"), _context()
        )

        assert artifact.status == "blocked"
        assert provider.requests[0].provider_model == "provider-model-b"
        assert provider.requests[0].credential == "unit-test-credential"
        assert "task_user_model" in provider.requests[0].messages[1].content
        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_adapter")
            calls = await ModelCallRepository(session).list_for_run(runs[0].agent_run_id)
        assert len(runs) == 1
        assert runs[0].model_id == "test:model-b"
        assert runs[0].model_provider == "test"
        assert runs[0].prompt_key == "agent:user_research"
        assert runs[0].input_tokens == 12
        assert len(calls) == 1
        assert calls[0].status == "completed"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_internal_adapter_fails_explicitly_when_prompt_is_unbound(
    tmp_path: Path,
) -> None:
    database = await _database(tmp_path)
    provider = ArtifactProvider()
    providers = ModelProviderRegistry()
    providers.register(provider)
    adapter = InternalModelAgentAdapter(
        ModelGateway(
            database,
            _catalog(),
            EnvironmentCredentialResolver({"TEST_MODEL_KEY": "unit-test-credential"}),
            providers,
        ),
        PromptRegistry(),
        ProjectModelSelectionResolver(database),
    )
    agents = AgentRegistry()
    agents.bind(ResearchAgentType.RED_TEAM, adapter)
    runtime = AgentRuntimeGateway(
        database,
        agents,
        ProjectEventBroker(),
        "trace_missing_prompt",
    )
    try:
        with pytest.raises(RuntimeGatewayError) as error:
            await runtime.execute(
                _task(ResearchAgentType.RED_TEAM, "task_red_missing_prompt"),
                _context(),
            )
        assert error.value.code is RuntimeErrorCode.DEPENDENCY_MISSING
        assert provider.requests == []
        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_adapter")
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error_code == RuntimeErrorCode.DEPENDENCY_MISSING
    finally:
        await database.dispose()
