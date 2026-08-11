from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.application.events import ProjectEventBroker
from app.application.runtime import (
    AgentInvocation,
    AgentRegistry,
    AgentRuntimeGateway,
    ArtifactStore,
)
from app.infrastructure.database import Database
from app.infrastructure.database.models import EvidenceModel, ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.schemas.project import DecisionAction, ProjectStatus, ResearchBrief
from app.workflows import (
    GateName,
    ResearchAgentType,
    StageDecision,
    WorkflowOutcome,
    compile_research_graph,
    create_initial_state,
)
from app.workflows.contracts import GateRequest
from app.workflows.planning import PLANNED_AGENT_TYPES
from tests.research_brief import home_safety_brief

from .workflow_runtime import TestAgentRuntime


class WorkflowAdapter:
    adapter_type = "test_workflow_adapter"

    def __init__(self) -> None:
        self.runtime = TestAgentRuntime()

    async def execute(self, invocation: AgentInvocation) -> object:
        return await self.runtime.execute(invocation.task, invocation.context)


def _brief() -> ResearchBrief:
    return home_safety_brief()


def _request(result: dict[str, Any]) -> GateRequest:
    return GateRequest.model_validate(result["__interrupt__"][0].value)


def _decision(
    request: GateRequest,
    action: DecisionAction,
    *,
    selected: list[str] | None = None,
) -> dict[str, Any]:
    return StageDecision(
        decision_id=request.decision_id,
        gate=request.gate,
        action=action,
        actor="Runtime integration test",
        reason=f"test:{action}",
        selected_innovation_ids=selected or [],
    ).model_dump(mode="json")


async def _seed(database: Database, project_id: str) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            ProjectModel(
                project_id=project_id,
                status=ProjectStatus.RESEARCHING,
                current_stage="runtime_integration",
                progress=10,
                brief_json=_brief().model_dump(mode="json"),
                pending_decision_json=None,
                created_at=now,
                updated_at=now,
            )
        )
        for suffix in ("user_research", "competitor_research"):
            session.add(
                EvidenceModel(
                    evidence_id=f"ev_test_{suffix}",
                    project_id=project_id,
                    collection_job_id=None,
                    source_url=f"https://example.com/{suffix}",
                    normalized_source_url=f"https://example.com/{suffix}",
                    source_domain="example.com",
                    source_type="test",
                    title=f"Test evidence {suffix}",
                    original_excerpt="Test-only evidence for graph integration.",
                    claim_type=EvidenceClaimType.FACT,
                    product="doorbell",
                    region="US",
                    user_segment=None,
                    published_at=now,
                    collected_at=now,
                    status=EvidenceStatus.VERIFIED,
                    content_hash=(suffix.encode().hex() + "0" * 64)[:64],
                    confidence=0.9,
                    authority_score=0.9,
                    recency_score=0.9,
                    diversity_score=0.8,
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_langgraph_runs_ai_native_phase_through_persistent_runtime_gateway(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'runtime-graph.db'}")
    await database.create_schema()
    try:
        project_id = "proj_runtime_graph"
        await _seed(database, project_id)
        registry = AgentRegistry()
        adapter = WorkflowAdapter()
        for agent_type in ResearchAgentType:
            registry.bind(agent_type, adapter)
        broker = ProjectEventBroker()
        gateway = AgentRuntimeGateway(
            database,
            registry,
            broker,
            "trace_runtime_graph",
        )
        graph = compile_research_graph(gateway, InMemorySaver())
        config = {
            "configurable": {"thread_id": project_id},
            "recursion_limit": 50,
        }

        result = await graph.ainvoke(create_initial_state(project_id, _brief()), config)
        assert _request(result).gate is GateName.BRIEF
        result = await graph.ainvoke(
            Command(resume=_decision(_request(result), DecisionAction.APPROVE)), config
        )
        assert _request(result).gate is GateName.AI_NATIVE_ECOSYSTEM
        result = await graph.ainvoke(
            Command(
                resume=_decision(
                    _request(result),
                    DecisionAction.APPROVE,
                    selected=["eco_continuous_guard"],
                )
            ),
            config,
        )

        assert result["outcome"] == WorkflowOutcome.AWAITING_SECURITY_POLICY
        async with database.session() as session:
            repository = ProjectRepository(session)
            runs = await repository.list_agent_runs(project_id)
            events = await repository.list_events(project_id, limit=200)
        main_path_types = {
            ResearchAgentType.RESEARCH_MANAGER,
            *PLANNED_AGENT_TYPES,
            ResearchAgentType.TECHNICAL_FEASIBILITY,
        }
        assert len(runs) == len(main_path_types)
        assert all(run.output_artifact_id is not None for run in runs)
        assert {run.agent_type for run in runs} == {item.value for item in main_path_types}
        assert [event.sequence_number for event in events] == list(
            range(1, len(events) + 1)
        )
        assert {event.event_type for event in events} >= {
            "agent_started",
            "artifact_created",
            "agent_completed",
        }
        manager_artifacts = await ArtifactStore(database).list_versions(
            project_id, f"task_{project_id}_plan"
        )
        assert len(manager_artifacts) == 1
        assert manager_artifacts[0].artifact.artifact_type == "research_manager"
    finally:
        await database.dispose()
