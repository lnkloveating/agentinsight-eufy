from datetime import UTC, datetime

import pytest

from app.application.events import ProjectEventBroker
from app.application.evidence import EvidenceService
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceIngest, EvidenceStatus


def _project(project_id: str) -> ProjectModel:
    now = datetime.now(UTC)
    return ProjectModel(
        project_id=project_id,
        status="opportunity_research",
        current_stage="evidence_collection",
        progress=20,
        brief_json={"question": "test"},
        pending_decision_json=None,
        created_at=now,
        updated_at=now,
    )


def _evidence(source_url: str, excerpt: str) -> EvidenceIngest:
    return EvidenceIngest(
        source_url=source_url,
        source_type="official",
        title="Official product page",
        original_excerpt=excerpt,
        claim_type=EvidenceClaimType.FACT,
        collected_at=datetime.now(UTC),
        status=EvidenceStatus.VERIFIED,
        confidence=0.9,
        authority_score=0.9,
        recency_score=0.8,
        diversity_score=0.7,
    )


@pytest.mark.asyncio
async def test_ingest_deduplicates_content_inside_one_project() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            session.add(_project("proj_one"))
            await session.commit()
            project_repository = ProjectRepository(session)
            broker = ProjectEventBroker()
            service = EvidenceService(
                EvidenceRepository(session),
                project_repository,
                "trace_test",
                broker,
            )

            first = await service.ingest(
                "proj_one",
                _evidence("https://www.example.com/report?utm_source=test", "Package demand rose."),
            )
            duplicate = await service.ingest(
                "proj_one",
                _evidence("https://example.com/another", "  package demand ROSE.  "),
            )

            assert first.created is True
            assert duplicate.created is False
            assert duplicate.evidence.evidence_id == first.evidence.evidence_id
            assert first.evidence.source_domain == "example.com"
            events = await project_repository.list_events("proj_one")
            assert [event.event_type for event in events] == ["evidence_added"]
            assert broker.current_version("proj_one") == 1
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_same_content_is_isolated_between_projects() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        async with database.session() as session:
            session.add_all([_project("proj_one"), _project("proj_two")])
            await session.commit()
            service = EvidenceService(
                EvidenceRepository(session),
                ProjectRepository(session),
                "trace_test",
                ProjectEventBroker(),
            )

            first = await service.ingest(
                "proj_one", _evidence("https://example.com/report", "Same finding")
            )
            second = await service.ingest(
                "proj_two", _evidence("https://example.com/report", "Same finding")
            )

            assert first.created is True
            assert second.created is True
            assert first.evidence.evidence_id != second.evidence.evidence_id
    finally:
        await database.dispose()
