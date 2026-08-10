from datetime import UTC, datetime

import pytest

from app.agents.competitor import (
    CompetitorA2ASupervisorAdapter,
    build_competitor_evidence_requests,
)
from app.application.events import ProjectEventBroker
from app.application.runtime import (
    AgentInvocation,
    AgentRegistry,
    AgentRuntimeGateway,
    CancellationToken,
)
from app.infrastructure.database import Database, ProjectModel
from app.infrastructure.database.a2a_repository import A2ATaskRepository
from app.integrations.a2a import A2ASpecialistRegistry, A2ATaskStatus, CompetitorA2AGateway
from app.schemas.project import ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
    ResearchTaskStatus,
)
from tests.research_brief import home_safety_brief


def _brief() -> ResearchBrief:
    return home_safety_brief()


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_competitor",
        project_id="project_supervisor",
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Build an evidence-backed competitor research artifact",
        scope={
            "target_product": "Authorized target",
            "selected_products": [
                {"model": "Authorized comparison"},
                {"category": "ignored without model"},
            ],
        },
        budget=ResearchBudget(max_pages=20, deadline_seconds=30),
    )


def _context() -> AgentContext:
    return AgentContext(
        project_id="project_supervisor",
        brief=_brief(),
        iteration=0,
    )


def test_supervisor_creates_three_stable_evidence_requests_without_claims() -> None:
    task = _task()
    invocation = AgentInvocation(
        agent_run_id="run_request_contract",
        trace_id="trace_request_contract",
        attempt_number=1,
        workspace_key="workspace",
        input_artifact_ids=(),
        task=task,
        context=_context(),
        cancellation_token=CancellationToken(),
    )

    first = build_competitor_evidence_requests(invocation)
    second = build_competitor_evidence_requests(invocation)

    assert first == second
    assert len(first) == 3
    assert len({request.specialist_type for request in first}) == 3
    assert all(
        request.product_scope == ["Authorized target", "Authorized comparison"]
        for request in first
    )
    assert all(not hasattr(request, "findings") for request in first)


@pytest.mark.asyncio
async def test_runtime_uses_competitor_supervisor_and_blocks_when_no_specialist_is_bound() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    broker = ProjectEventBroker()
    now = datetime.now(UTC)
    try:
        async with database.session() as session:
            session.add(
                ProjectModel(
                    project_id="project_supervisor",
                    status=ProjectStatus.RESEARCHING,
                    current_stage="parallel_research",
                    progress=20,
                    brief_json=_brief().model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

        specialist_registry = A2ASpecialistRegistry()
        supervisor = CompetitorA2ASupervisorAdapter(
            CompetitorA2AGateway(database, specialist_registry, broker)
        )
        agent_registry = AgentRegistry()
        agent_registry.bind(ResearchAgentType.COMPETITOR_RESEARCH, supervisor)
        runtime = AgentRuntimeGateway(
            database,
            agent_registry,
            broker,
            "trace_supervisor_runtime",
        )

        artifact = await runtime.execute(_task(), _context())

        assert artifact.status is ResearchTaskStatus.BLOCKED
        assert artifact.payload["schema_name"] == "competitor_a2a_foundation"
        assert artifact.payload["specialist_outputs"] == []
        assert artifact.payload["synthesis_status"] == "not_implemented_in_foundation"
        assert artifact.evidence_ids == []
        assert len(artifact.unknowns) == 3
        async with database.session() as session:
            tasks = await A2ATaskRepository(session).list_for_parent(
                "project_supervisor", "task_competitor"
            )
        assert len(tasks) == 3
        assert all(task.status == A2ATaskStatus.BLOCKED for task in tasks)
        assert all(task.output_json is None for task in tasks)
    finally:
        await database.dispose()

