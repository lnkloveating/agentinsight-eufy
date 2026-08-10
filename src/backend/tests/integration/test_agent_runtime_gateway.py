import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from app.application.events import ProjectEventBroker
from app.application.runtime import (
    AgentInvocation,
    AgentRegistry,
    AgentRuntimeGateway,
    ArtifactAccessDeniedError,
    ArtifactStore,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.infrastructure.database import Database
from app.infrastructure.database.models import EvidenceModel, ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.runtime_repository import AgentRuntimeRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.schemas.project import AgentRunStatus, ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)
from tests.research_brief import home_safety_brief


class StaticAdapter:
    adapter_type = "test_static"

    def __init__(self, factory: Callable[[AgentInvocation], object]) -> None:
        self.factory = factory
        self.invocations: list[AgentInvocation] = []

    async def execute(self, invocation: AgentInvocation) -> object:
        self.invocations.append(invocation)
        invocation.cancellation_token.raise_if_cancelled()
        return self.factory(invocation)


class SlowAdapter:
    adapter_type = "test_slow"

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, invocation: AgentInvocation) -> object:
        self.started.set()
        await asyncio.Event().wait()
        return _artifact(invocation, "ev_unused")


def _brief() -> ResearchBrief:
    return home_safety_brief()


def _task(
    project_id: str,
    agent_type: ResearchAgentType = ResearchAgentType.USER_RESEARCH,
    *,
    task_id: str | None = None,
) -> ResearchTask:
    return ResearchTask(
        task_id=task_id or f"task_{project_id}_{agent_type}",
        project_id=project_id,
        agent_type=agent_type,
        goal=f"test:{agent_type}",
    )


def _context(
    project_id: str,
    upstream: dict[str, ResearchArtifact] | None = None,
) -> AgentContext:
    return AgentContext(
        project_id=project_id,
        brief=_brief(),
        iteration=0,
        upstream_artifacts=upstream or {},
    )


def _artifact(
    invocation: AgentInvocation,
    evidence_id: str,
    *,
    status: ResearchTaskStatus = ResearchTaskStatus.COMPLETED,
) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id=f"adapter_{invocation.task.task_id}_{invocation.attempt_number}",
        task_id=invocation.task.task_id,
        artifact_type=invocation.task.agent_type,
        status=status,
        payload={"attempt": invocation.attempt_number},
        evidence_ids=[evidence_id] if evidence_id else [],
        quality_score=88,
    )


async def _seed(database: Database, *project_ids: str) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        for project_id in project_ids:
            session.add(
                ProjectModel(
                    project_id=project_id,
                    status=ProjectStatus.RESEARCHING,
                    current_stage="runtime_test",
                    progress=20,
                    brief_json=_brief().model_dump(mode="json"),
                    pending_decision_json=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                EvidenceModel(
                    evidence_id=f"ev_{project_id}",
                    project_id=project_id,
                    collection_job_id=None,
                    source_url=f"https://example.com/{project_id}",
                    normalized_source_url=f"https://example.com/{project_id}",
                    source_domain="example.com",
                    source_type="official",
                    title="Runtime test evidence",
                    original_excerpt="Test-only evidence for runtime persistence.",
                    claim_type=EvidenceClaimType.FACT,
                    product="doorbell",
                    region="US",
                    user_segment=None,
                    published_at=now,
                    collected_at=now,
                    status=EvidenceStatus.VERIFIED,
                    content_hash=(project_id.encode().hex() + "0" * 64)[:64],
                    confidence=0.9,
                    authority_score=0.9,
                    recency_score=0.9,
                    diversity_score=0.8,
                )
            )
        await session.commit()


def _gateway(
    database: Database,
    registry: AgentRegistry,
    broker: ProjectEventBroker | None = None,
    *,
    max_timeout_seconds: float | None = None,
) -> AgentRuntimeGateway:
    return AgentRuntimeGateway(
        database,
        registry,
        broker or ProjectEventBroker(),
        "trace_runtime_test",
        max_timeout_seconds=max_timeout_seconds,
    )


@pytest.mark.asyncio
async def test_gateway_persists_run_events_artifact_versions_and_lineage() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        await _seed(database, "proj_one")
        registry = AgentRegistry()
        user_adapter = StaticAdapter(
            lambda invocation: _artifact(invocation, "ev_proj_one")
        )
        product_adapter = StaticAdapter(
            lambda invocation: _artifact(invocation, "ev_proj_one")
        )
        registry.bind(ResearchAgentType.USER_RESEARCH, user_adapter)
        registry.bind(ResearchAgentType.PRODUCT_TECHNICAL, product_adapter)
        broker = ProjectEventBroker()
        gateway = _gateway(database, registry, broker)

        first = await gateway.execute(_task("proj_one"), _context("proj_one"))
        second = await gateway.execute(_task("proj_one"), _context("proj_one"))
        downstream = await gateway.execute(
            _task("proj_one", ResearchAgentType.PRODUCT_TECHNICAL),
            _context("proj_one", {"user_research": second}),
        )

        store = ArtifactStore(database)
        versions = await store.list_versions("proj_one", _task("proj_one").task_id)
        stored_downstream = await store.get("proj_one", downstream.artifact_id)
        assert [item.version for item in versions] == [1, 2]
        assert first.artifact_id != second.artifact_id
        assert stored_downstream is not None
        assert stored_downstream.input_artifact_ids == (second.artifact_id,)
        assert len(stored_downstream.content_hash) == 64

        async with database.session() as session:
            project_repository = ProjectRepository(session)
            runs = await project_repository.list_agent_runs("proj_one")
            events = await project_repository.list_events("proj_one", limit=100)
        attempts = [
            run.attempt_number
            for run in runs
            if run.task_id == _task("proj_one").task_id
        ]
        assert sorted(attempts) == [1, 2]
        assert all(run.status == AgentRunStatus.COMPLETED for run in runs)
        assert all(run.output_artifact_id for run in runs)
        assert {event.event_type for event in events} >= {
            "agent_run_created",
            "agent_started",
            "artifact_created",
            "agent_completed",
        }
        assert broker.current_version("proj_one") == 6
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_gateway_rejects_cross_project_artifact_and_store_hides_it() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        await _seed(database, "proj_one", "proj_two")
        registry = AgentRegistry()
        adapter = StaticAdapter(
            lambda invocation: _artifact(
                invocation, f"ev_{invocation.task.project_id}"
            )
        )
        registry.bind(ResearchAgentType.USER_RESEARCH, adapter)
        registry.bind(ResearchAgentType.PRODUCT_TECHNICAL, adapter)
        gateway = _gateway(database, registry)
        first = await gateway.execute(_task("proj_one"), _context("proj_one"))

        with pytest.raises(RuntimeGatewayError) as exc_info:
            await gateway.execute(
                _task("proj_two", ResearchAgentType.PRODUCT_TECHNICAL),
                _context("proj_two", {"user_research": first}),
            )
        assert exc_info.value.code is RuntimeErrorCode.PERMISSION_DENIED

        with pytest.raises(ArtifactAccessDeniedError):
            await ArtifactStore(database).get("proj_two", first.artifact_id)
        assert await ArtifactStore(database).get("proj_one", first.artifact_id) is not None
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_gateway_classifies_unbound_invalid_schema_and_mock_evidence() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        await _seed(database, "proj_one")
        registry = AgentRegistry()
        gateway = _gateway(database, registry)
        manager_task = _task("proj_one", ResearchAgentType.RESEARCH_MANAGER)

        with pytest.raises(RuntimeGatewayError) as unbound:
            await gateway.execute(manager_task, _context("proj_one"))
        assert unbound.value.code is RuntimeErrorCode.RUNTIME_NOT_BOUND

        registry.bind(
            ResearchAgentType.USER_RESEARCH,
            StaticAdapter(lambda invocation: {"bad": True}),
        )
        with pytest.raises(RuntimeGatewayError) as invalid_schema:
            await gateway.execute(_task("proj_one"), _context("proj_one"))
        assert invalid_schema.value.code is RuntimeErrorCode.SCHEMA_INVALID

        mock_adapter = StaticAdapter(lambda invocation: _artifact(invocation, "ev_mock"))
        registry.bind(ResearchAgentType.USER_RESEARCH, mock_adapter, replace=True)
        with pytest.raises(RuntimeGatewayError) as invalid_evidence:
            await gateway.execute(_task("proj_one"), _context("proj_one"))
        assert invalid_evidence.value.code is RuntimeErrorCode.ARTIFACT_INVALID

        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_one")
            artifacts = await AgentRuntimeRepository(session).list_task_artifacts(
                "proj_one", _task("proj_one").task_id
            )
        assert {run.error_code for run in runs} == {
            RuntimeErrorCode.RUNTIME_NOT_BOUND,
            RuntimeErrorCode.SCHEMA_INVALID,
            RuntimeErrorCode.ARTIFACT_INVALID,
        }
        assert artifacts == []
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_gateway_classifies_timeout_and_cancellation_without_artifact() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        await _seed(database, "proj_one")
        registry = AgentRegistry()
        timeout_adapter = SlowAdapter()
        registry.bind(ResearchAgentType.USER_RESEARCH, timeout_adapter)
        timeout_gateway = _gateway(database, registry, max_timeout_seconds=0.02)
        with pytest.raises(RuntimeGatewayError) as timeout_error:
            await timeout_gateway.execute(_task("proj_one"), _context("proj_one"))
        assert timeout_error.value.code is RuntimeErrorCode.TIMEOUT

        cancel_adapter = SlowAdapter()
        registry.bind(ResearchAgentType.USER_RESEARCH, cancel_adapter, replace=True)
        cancel_gateway = _gateway(database, registry)
        execution = asyncio.create_task(
            cancel_gateway.execute(
                _task("proj_one", task_id="task_cancel"),
                _context("proj_one"),
            )
        )
        await cancel_adapter.started.wait()
        active_ids = await cancel_gateway.active_run_ids()
        assert len(active_ids) == 1
        assert await cancel_gateway.cancel(active_ids[0]) is True
        with pytest.raises(RuntimeGatewayError) as cancelled:
            await execution
        assert cancelled.value.code is RuntimeErrorCode.CANCELLED
        assert await cancel_gateway.cancel("run_missing") is False

        async with database.session() as session:
            runs = await ProjectRepository(session).list_agent_runs("proj_one")
            timeout_artifacts = await AgentRuntimeRepository(session).list_task_artifacts(
                "proj_one", _task("proj_one").task_id
            )
            cancelled_artifacts = await AgentRuntimeRepository(session).list_task_artifacts(
                "proj_one", "task_cancel"
            )
        statuses = {run.task_id: run.status for run in runs}
        assert statuses[_task("proj_one").task_id] == AgentRunStatus.FAILED
        assert statuses["task_cancel"] == AgentRunStatus.CANCELLED
        assert timeout_artifacts == []
        assert cancelled_artifacts == []
    finally:
        await database.dispose()
