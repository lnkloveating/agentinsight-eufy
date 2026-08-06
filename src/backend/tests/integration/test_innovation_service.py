from datetime import UTC, datetime

import pytest

from app.application.events import ProjectEventBroker
from app.application.innovations import InnovationService
from app.core.errors import AppError
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.innovation_repository import InnovationRepository
from app.infrastructure.database.models import EvidenceModel, ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceStatus
from app.schemas.innovation import (
    ContextSignal,
    EventReference,
    EventUnderstanding,
    InnovationCreate,
    InnovationScoreInput,
    InnovationStatus,
    ProblemDefinition,
    RedTeamDecision,
    RedTeamReview,
    RedTeamSeverity,
    ScoreComponent,
    ScoreDimension,
    SignalAvailability,
    TargetUser,
)


def _project(project_id: str) -> ProjectModel:
    now = datetime.now(UTC)
    return ProjectModel(
        project_id=project_id,
        status="opportunity_research",
        current_stage="scenario_comparison",
        progress=55,
        brief_json={"question": "test"},
        pending_decision_json=None,
        created_at=now,
        updated_at=now,
    )


def _evidence(evidence_id: str, project_id: str, status: EvidenceStatus) -> EvidenceModel:
    now = datetime.now(UTC)
    return EvidenceModel(
        evidence_id=evidence_id,
        project_id=project_id,
        source_url=f"https://example.com/{evidence_id}",
        normalized_source_url=f"https://example.com/{evidence_id}",
        source_domain="example.com",
        source_type="official",
        title=evidence_id,
        original_excerpt=f"Excerpt for {evidence_id}",
        claim_type="fact",
        collected_at=now,
        status=status,
        content_hash=evidence_id.removeprefix("ev_").ljust(64, "0"),
        confidence=0.9,
        authority_score=0.9,
        recency_score=0.9,
        diversity_score=0.9,
    )


def _signal(signal_type: str) -> ContextSignal:
    return ContextSignal(
        type=signal_type,
        source=f"source:{signal_type}",
        availability=SignalAvailability.AVAILABLE,
        authorization="authorized for the research scope",
        freshness="within five minutes",
        latency_ms=100,
        confidence=0.9,
        fallback="return an inconclusive result",
    )


def _create_payload(*evidence_ids: str) -> InnovationCreate:
    return InnovationCreate(
        name="Candidate under test",
        target_user=TargetUser(description="Doorbell owner"),
        problem=ProblemDefinition(description="Notifications lack context"),
        event_understanding=EventUnderstanding(
            base_event=EventReference(type="package_delivered", source="doorbell"),
            event_state=EventReference(type="package_still_present", source="doorbell"),
            context_signals=[_signal("weather"), _signal("package_presence")],
            inference="The package may remain exposed.",
            risk_or_value="Possible weather damage.",
            recommended_action="Ask the resident to review the event.",
        ),
        competitor_gap_ids=["gap_context_reasoning"],
        technical_assessment={"feasible": True},
        business_assessment={"recommendation": "investigate"},
        evidence_ids=list(evidence_ids),
    )


def _score_payload(evidence_id: str) -> InnovationScoreInput:
    return InnovationScoreInput(
        score_breakdown={
            dimension: ScoreComponent(
                score=80,
                weight=1 / len(ScoreDimension),
                rationale=f"Rationale for {dimension.value}",
                evidence_ids=[evidence_id],
            )
            for dimension in ScoreDimension
        }
    )


def _service(
    database_session: object,
    broker: ProjectEventBroker,
) -> InnovationService:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(database_session, AsyncSession)
    return InnovationService(
        InnovationRepository(database_session),
        EvidenceRepository(database_session),
        ProjectRepository(database_session),
        "trace_innovation",
        broker,
    )


@pytest.mark.asyncio
async def test_creation_keeps_only_valid_same_project_evidence() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            session.add_all(
                [
                    _project("proj_one"),
                    _project("proj_two"),
                    _evidence("ev_valid", "proj_one", EvidenceStatus.VERIFIED),
                    _evidence("ev_mock", "proj_one", EvidenceStatus.MOCK),
                    _evidence("ev_cross", "proj_two", EvidenceStatus.VERIFIED),
                ]
            )
            await session.commit()

            innovation = await _service(session, ProjectEventBroker()).create(
                "proj_one", _create_payload("ev_valid", "ev_mock", "ev_cross")
            )

            assert innovation.status is InnovationStatus.EVIDENCE_PENDING
            assert innovation.evidence_ids == ["ev_valid"]
            assert innovation.gate_issues == [
                "evidence_status_not_eligible:ev_mock:mock",
                "evidence_cross_project:ev_cross",
            ]
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_creation_rejects_candidate_when_all_evidence_is_mock() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            session.add_all(
                [
                    _project("proj_one"),
                    _evidence("ev_mock", "proj_one", EvidenceStatus.MOCK),
                ]
            )
            await session.commit()
            service = _service(session, ProjectEventBroker())

            with pytest.raises(AppError) as exc_info:
                await service.create("proj_one", _create_payload("ev_mock"))

            assert exc_info.value.code == "INNOVATION_EVIDENCE_REQUIRED"
            assert await InnovationRepository(session).list_by_project("proj_one") == []
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_scoring_and_red_team_change_score_status_and_events() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    broker = ProjectEventBroker()
    try:
        async with database.session() as session:
            session.add_all(
                [
                    _project("proj_one"),
                    _evidence("ev_valid", "proj_one", EvidenceStatus.VERIFIED),
                ]
            )
            await session.commit()
            service = _service(session, broker)

            created = await service.create("proj_one", _create_payload("ev_valid"))
            scored = await service.score(
                "proj_one", created.innovation_id, _score_payload("ev_valid")
            )
            reviewed = await service.apply_red_team(
                "proj_one",
                created.innovation_id,
                RedTeamReview(
                    severity=RedTeamSeverity.HIGH,
                    technical_risks=["The context signal is not yet production proven"],
                    required_actions=["Run a consented device experiment"],
                    score_adjustments={ScoreDimension.TECHNICAL_DATA_FEASIBILITY: -40},
                    decision=RedTeamDecision.REVISE,
                ),
            )
            events = await ProjectRepository(session).list_events("proj_one")

            assert created.status is InnovationStatus.BUSINESS_REVIEW
            assert scored.status is InnovationStatus.RED_TEAM_REVIEW
            assert scored.base_score == 80
            assert reviewed.status is InnovationStatus.NEEDS_REVISION
            assert reviewed.final_score == 75
            assert [event.event_type for event in events] == [
                "innovation_scored",
                "red_team_reviewed",
            ]
            assert broker.current_version("proj_one") == 2
    finally:
        await database.dispose()
