from datetime import UTC, datetime

import pytest

from app.application.events import ProjectEventBroker
from app.application.evidence import CollectionJobService
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import (
    CollectionJobCreate,
    CollectionJobFailure,
    CollectionJobStatus,
)


@pytest.mark.asyncio
async def test_collection_failure_is_persisted_and_emitted_as_coverage_gap() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    broker = ProjectEventBroker()
    try:
        async with database.session() as session:
            now = datetime.now(UTC)
            session.add(
                ProjectModel(
                    project_id="proj_one",
                    status="opportunity_research",
                    current_stage="evidence_collection",
                    progress=20,
                    brief_json={"question": "test"},
                    pending_decision_json=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            project_repository = ProjectRepository(session)
            service = CollectionJobService(
                EvidenceRepository(session),
                project_repository,
                "trace_collection",
                broker,
            )

            job = await service.create(
                "proj_one",
                CollectionJobCreate(
                    source_url="https://retailer.example/products",
                    source_type="retail",
                ),
            )
            failed = await service.record_failure(
                job.collection_job_id,
                CollectionJobFailure(
                    attempt_count=2,
                    error_code="ROBOTS_BLOCKED",
                    error_message="The source refused automated access",
                ),
            )
            events = await project_repository.list_events("proj_one")

            assert failed.status is CollectionJobStatus.FAILED
            assert failed.attempt_count == 2
            assert failed.error_code == "ROBOTS_BLOCKED"
            assert events[-1].event_type == "evidence_collection_failed"
            assert events[-1].data_json["coverage_gap"] is True
            assert broker.current_version("proj_one") == 1
    finally:
        await database.dispose()
