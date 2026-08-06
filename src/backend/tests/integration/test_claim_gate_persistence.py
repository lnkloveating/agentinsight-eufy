from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.application.events import ProjectEventBroker
from app.application.evidence import ClaimService
from app.infrastructure.database import Database
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import (
    ClaimEvidenceLinkModel,
    EvidenceModel,
    ProjectModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import ClaimCreate, ClaimStatus, ClaimType, EvidenceStatus


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


@pytest.mark.asyncio
async def test_claim_gate_persists_only_eligible_same_project_links() -> None:
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
            project_repository = ProjectRepository(session)
            broker = ProjectEventBroker()
            service = ClaimService(
                EvidenceRepository(session),
                project_repository,
                "trace_test",
                broker,
            )

            result = await service.create_and_evaluate(
                "proj_one",
                ClaimCreate(
                    statement="A factual statement",
                    claim_type=ClaimType.FACT,
                    evidence_ids=["ev_valid", "ev_mock", "ev_cross", "ev_missing"],
                ),
            )

            links = list(await session.scalars(select(ClaimEvidenceLinkModel)))
            assert result.claim.status is ClaimStatus.SUPPORTED
            assert result.claim.evidence_ids == ["ev_valid"]
            assert result.rejected_evidence_ids == {
                "ev_mock": "status:mock",
                "ev_cross": "cross_project",
                "ev_missing": "not_found",
            }
            assert len(links) == 1
            assert links[0].evidence_id == "ev_valid"
            assert links[0].relation_type == "supports"
            events = await project_repository.list_events("proj_one")
            assert events[-1].event_type == "claim_evaluated"
            assert events[-1].data_json["eligible_for_factual_use"] is True
            assert broker.current_version("proj_one") == 1
    finally:
        await database.dispose()
