import asyncio
import hashlib
from datetime import UTC, datetime

import pytest

from app.application.events import ProjectEventBroker
from app.application.runtime import CancellationToken
from app.infrastructure.database import AgentRunModel, Database, ProjectModel
from app.infrastructure.database.a2a_repository import A2ATaskRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.integrations.a2a import (
    A2AErrorCode,
    A2ASpecialistInvocation,
    A2ASpecialistRegistry,
    A2ATaskStatus,
    CompetitorA2ABatchError,
    CompetitorA2AGateway,
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
    EvidenceRequest,
)
from app.schemas.project import AgentRunStatus, ProjectStatus, ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    AgentEvidence,
    AgentEvidenceContext,
    ResearchAgentType,
    ResearchTaskStatus,
)


def _brief() -> ResearchBrief:
    return ResearchBrief(
        question="Research a future opportunity in home security products",
        category="home security",
        target_user="households",
        region="US",
        scenarios=["front door"],
    )


def _evidence(
    evidence_id: str,
    claim_type: str,
    domain: str,
) -> AgentEvidence:
    return AgentEvidence(
        evidence_id=evidence_id,
        title="Test evidence",
        original_excerpt="A deterministic test excerpt, not a production claim.",
        claim_type=claim_type,
        status="verified",
        source_type="webpage",
        source_url=f"https://{domain}/source",
        source_domain=domain,
        confidence=0.9,
        authority_score=0.8,
        recency_score=0.8,
        diversity_score=0.8,
    )


def _context() -> AgentContext:
    items = [
        _evidence("ev_vendor", "vendor_claim", "vendor.example"),
        _evidence("ev_fact", "fact", "channel.example"),
        _evidence("ev_opinion", "user_opinion", "review.example"),
    ]
    context_hash = hashlib.sha256(
        "|".join(item.evidence_id for item in items).encode()
    ).hexdigest()
    return AgentContext(
        project_id="project_a2a",
        brief=_brief(),
        iteration=0,
        evidence_context=AgentEvidenceContext(
            items=items,
            available_evidence_count=len(items),
            included_evidence_count=len(items),
            omitted_evidence_count=0,
            context_hash=context_hash,
        ),
    )


def _requests() -> list[EvidenceRequest]:
    common = {
        "project_id": "project_a2a",
        "parent_task_id": "task_competitor_research",
        "product_scope": ["authorized target"],
        "region": "US",
        "minimum_independent_domains": 1,
    }
    return [
        EvidenceRequest(
            **common,
            request_id="request_official",
            specialist_type=CompetitorSpecialistType.OFFICIAL_PRODUCT,
            research_questions=["What official capabilities are evidenced?"],
            evidence_types=["official_product_page"],
            allowed_claim_types=["vendor_claim"],
        ),
        EvidenceRequest(
            **common,
            request_id="request_price",
            specialist_type=CompetitorSpecialistType.PRICE_CHANNEL,
            research_questions=["What price and channel facts are evidenced?"],
            evidence_types=["authorized_channel_page"],
            allowed_claim_types=["fact"],
        ),
        EvidenceRequest(
            **common,
            request_id="request_review",
            specialist_type=CompetitorSpecialistType.USER_REVIEW,
            research_questions=["What user opinions are evidenced?"],
            evidence_types=["authorized_user_review"],
            allowed_claim_types=["user_opinion"],
        ),
    ]


async def _seed(database: Database, parent_run_id: str = "run_competitor") -> None:
    await database.create_schema()
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            ProjectModel(
                project_id="project_a2a",
                status=ProjectStatus.RESEARCHING,
                current_stage="parallel_research",
                progress=20,
                brief_json=_brief().model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AgentRunModel(
                agent_run_id=parent_run_id,
                project_id="project_a2a",
                task_id="task_competitor_research",
                agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
                agent_name="Competitor supervisor",
                adapter_type="competitor-a2a-supervisor",
                attempt_number=1,
                workspace_key="project_a2a/task_competitor_research/attempt-1",
                trace_id="trace_a2a",
                timeout_seconds=30,
                input_artifact_ids_json=[],
                status=AgentRunStatus.RUNNING,
                progress=5,
                quality_score=0,
                evidence_ids_json=[],
                unknowns_json=[],
                message="Test parent run",
                started_at=now,
            )
        )
        await session.commit()


def _artifact(invocation: A2ASpecialistInvocation) -> CompetitorSpecialistArtifact:
    evidence_id = {
        CompetitorSpecialistType.OFFICIAL_PRODUCT: "ev_vendor",
        CompetitorSpecialistType.PRICE_CHANNEL: "ev_fact",
        CompetitorSpecialistType.USER_REVIEW: "ev_opinion",
    }[invocation.request.specialist_type]
    return CompetitorSpecialistArtifact(
        a2a_task_id=invocation.a2a_task_id,
        request_id=invocation.request.request_id,
        specialist_type=invocation.request.specialist_type,
        status=ResearchTaskStatus.COMPLETED,
        findings=[
            CompetitorFinding(
                finding_id=f"finding_{invocation.request.specialist_type}",
                category="test_contract",
                statement="A test-only statement backed by the declared Evidence ID.",
                evidence_ids=[evidence_id],
                confidence=0.8,
            )
        ],
        evidence_ids=[evidence_id],
        quality_score=80,
    )


class RecordingAdapter:
    adapter_type = "recording-test-adapter"

    def __init__(
        self,
        calls: dict[CompetitorSpecialistType, int],
        started: list[CompetitorSpecialistType] | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self.calls = calls
        self.started = started
        self.release = release

    async def execute(
        self,
        invocation: A2ASpecialistInvocation,
    ) -> CompetitorSpecialistArtifact:
        specialist_type = invocation.request.specialist_type
        self.calls[specialist_type] = self.calls.get(specialist_type, 0) + 1
        if self.started is not None and self.release is not None:
            self.started.append(specialist_type)
            if len(self.started) == 3:
                self.release.set()
            await asyncio.wait_for(self.release.wait(), timeout=0.5)
        return _artifact(invocation)


class FailOnceAdapter(RecordingAdapter):
    async def execute(
        self,
        invocation: A2ASpecialistInvocation,
    ) -> CompetitorSpecialistArtifact:
        specialist_type = invocation.request.specialist_type
        self.calls[specialist_type] = self.calls.get(specialist_type, 0) + 1
        if self.calls[specialist_type] == 1:
            raise RuntimeError("test-only first attempt failure")
        return _artifact(invocation)


@pytest.mark.asyncio
async def test_unbound_specialists_are_explicitly_blocked_without_fake_output() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        gateway = CompetitorA2AGateway(
            database, A2ASpecialistRegistry(), ProjectEventBroker()
        )
        results = await gateway.execute_all(
            parent_agent_run_id="run_competitor",
            trace_id="trace_a2a",
            requests=_requests(),
            context=_context(),
            cancellation_token=CancellationToken(),
        )

        assert {result.status for result in results} == {A2ATaskStatus.BLOCKED}
        assert all(result.artifact is None for result in results)
        assert all(
            result.error_code is A2AErrorCode.SPECIALIST_NOT_BOUND for result in results
        )
        async with database.session() as session:
            tasks = await A2ATaskRepository(session).list_for_parent(
                "project_a2a", "task_competitor_research"
            )
            events = await ProjectRepository(session).list_events("project_a2a")
        assert len(tasks) == 3
        assert all(task.status == A2ATaskStatus.BLOCKED for task in tasks)
        assert all(task.output_json is None for task in tasks)
        assert [event.event_type for event in events] == ["a2a_task_blocked"] * 3
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_three_bound_specialists_start_in_parallel_and_persist_evidence() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        calls: dict[CompetitorSpecialistType, int] = {}
        started: list[CompetitorSpecialistType] = []
        release = asyncio.Event()
        registry = A2ASpecialistRegistry()
        for specialist_type in CompetitorSpecialistType:
            registry.bind(
                specialist_type,
                RecordingAdapter(calls, started, release),
            )
        gateway = CompetitorA2AGateway(database, registry, ProjectEventBroker())

        results = await gateway.execute_all(
            parent_agent_run_id="run_competitor",
            trace_id="trace_parallel",
            requests=_requests(),
            context=_context(),
            cancellation_token=CancellationToken(),
        )

        assert len(started) == 3
        assert set(started) == set(CompetitorSpecialistType)
        assert all(result.status is A2ATaskStatus.COMPLETED for result in results)
        assert all(result.artifact and result.artifact.evidence_ids for result in results)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_retry_reuses_successful_specialists_and_only_reruns_failed_task() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        calls: dict[CompetitorSpecialistType, int] = {}
        registry = A2ASpecialistRegistry()
        registry.bind(
            CompetitorSpecialistType.OFFICIAL_PRODUCT,
            RecordingAdapter(calls),
        )
        registry.bind(
            CompetitorSpecialistType.PRICE_CHANNEL,
            RecordingAdapter(calls),
        )
        registry.bind(
            CompetitorSpecialistType.USER_REVIEW,
            FailOnceAdapter(calls),
        )
        gateway = CompetitorA2AGateway(database, registry, ProjectEventBroker())
        arguments = {
            "parent_agent_run_id": "run_competitor",
            "trace_id": "trace_retry",
            "requests": _requests(),
            "context": _context(),
            "cancellation_token": CancellationToken(),
        }

        with pytest.raises(CompetitorA2ABatchError) as first_failure:
            await gateway.execute_all(**arguments)
        results = await gateway.execute_all(**arguments)

        assert first_failure.value.failures[0].code is A2AErrorCode.ADAPTER_FAILED
        assert calls == {
            CompetitorSpecialistType.OFFICIAL_PRODUCT: 1,
            CompetitorSpecialistType.PRICE_CHANNEL: 1,
            CompetitorSpecialistType.USER_REVIEW: 2,
        }
        assert sum(result.reused for result in results) == 2
        review_result = next(
            result
            for result in results
            if result.request.specialist_type is CompetitorSpecialistType.USER_REVIEW
        )
        assert review_result.attempt_number == 2
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_unavailable_evidence_is_rejected_and_classified() -> None:
    class InvalidCitationAdapter:
        adapter_type = "invalid-citation-test-adapter"

        async def execute(self, invocation: A2ASpecialistInvocation) -> object:
            artifact = _artifact(invocation)
            return artifact.model_copy(
                update={
                    "findings": [
                        artifact.findings[0].model_copy(
                            update={"evidence_ids": ["ev_not_available"]}
                        )
                    ],
                    "evidence_ids": ["ev_not_available"],
                }
            )

    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        registry = A2ASpecialistRegistry()
        registry.bind(
            CompetitorSpecialistType.OFFICIAL_PRODUCT,
            InvalidCitationAdapter(),
        )
        gateway = CompetitorA2AGateway(database, registry, ProjectEventBroker())

        with pytest.raises(CompetitorA2ABatchError) as failure:
            await gateway.execute_all(
                parent_agent_run_id="run_competitor",
                trace_id="trace_invalid",
                requests=[_requests()[0]],
                context=_context(),
                cancellation_token=CancellationToken(),
            )

        assert failure.value.failures[0].code is A2AErrorCode.ARTIFACT_INVALID
        async with database.session() as session:
            tasks = await A2ATaskRepository(session).list_for_parent(
                "project_a2a", "task_competitor_research"
            )
        assert tasks[0].status == A2ATaskStatus.FAILED
        assert tasks[0].output_json is None
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_specialist_timeout_is_retryable_and_audited() -> None:
    class SlowAdapter:
        adapter_type = "slow-test-adapter"

        async def execute(self, invocation: A2ASpecialistInvocation) -> object:
            await asyncio.sleep(1)
            return _artifact(invocation)

    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        registry = A2ASpecialistRegistry()
        registry.bind(CompetitorSpecialistType.OFFICIAL_PRODUCT, SlowAdapter())
        gateway = CompetitorA2AGateway(
            database,
            registry,
            ProjectEventBroker(),
            specialist_timeout_seconds=0.01,
        )

        with pytest.raises(CompetitorA2ABatchError) as failure:
            await gateway.execute_all(
                parent_agent_run_id="run_competitor",
                trace_id="trace_timeout",
                requests=[_requests()[0]],
                context=_context(),
                cancellation_token=CancellationToken(),
            )

        assert failure.value.failures[0].code is A2AErrorCode.TIMEOUT
        assert failure.value.failures[0].retryable is True
        async with database.session() as session:
            tasks = await A2ATaskRepository(session).list_for_parent(
                "project_a2a", "task_competitor_research"
            )
        assert tasks[0].status == A2ATaskStatus.FAILED
        assert tasks[0].error_code == A2AErrorCode.TIMEOUT
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_pre_cancelled_batch_marks_bound_specialist_cancelled() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        registry = A2ASpecialistRegistry()
        registry.bind(
            CompetitorSpecialistType.OFFICIAL_PRODUCT,
            RecordingAdapter({}),
        )
        gateway = CompetitorA2AGateway(database, registry, ProjectEventBroker())
        token = CancellationToken()
        token.cancel()

        with pytest.raises(CompetitorA2ABatchError) as failure:
            await gateway.execute_all(
                parent_agent_run_id="run_competitor",
                trace_id="trace_cancelled",
                requests=[_requests()[0]],
                context=_context(),
                cancellation_token=token,
            )

        assert failure.value.failures[0].code is A2AErrorCode.CANCELLED
        async with database.session() as session:
            tasks = await A2ATaskRepository(session).list_for_parent(
                "project_a2a", "task_competitor_research"
            )
        assert tasks[0].status == A2ATaskStatus.CANCELLED
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_changed_evidence_context_invalidates_all_reusable_results() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await _seed(database)
    try:
        calls: dict[CompetitorSpecialistType, int] = {}
        registry = A2ASpecialistRegistry()
        for specialist_type in CompetitorSpecialistType:
            registry.bind(specialist_type, RecordingAdapter(calls))
        gateway = CompetitorA2AGateway(database, registry, ProjectEventBroker())
        original_context = _context()

        first = await gateway.execute_all(
            parent_agent_run_id="run_competitor",
            trace_id="trace_original_context",
            requests=_requests(),
            context=original_context,
            cancellation_token=CancellationToken(),
        )
        changed_context = original_context.model_copy(
            update={
                "evidence_context": original_context.evidence_context.model_copy(
                    update={"context_hash": "a" * 64}
                )
                if original_context.evidence_context is not None
                else None
            }
        )
        second = await gateway.execute_all(
            parent_agent_run_id="run_competitor",
            trace_id="trace_changed_context",
            requests=_requests(),
            context=changed_context,
            cancellation_token=CancellationToken(),
        )

        assert all(not result.reused for result in first + second)
        assert set(calls.values()) == {2}
    finally:
        await database.dispose()
